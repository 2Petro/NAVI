#!/usr/bin/env python3
"""
Nafy Controller - Optimized Hospital Dispatch API
------------------------------------------------
Single ROS2 node acting as the robot's control API.
Handles: Call Nafy / Reserve Nafy / End Task with queue + interruptible return-home.

Optimizations:
- Only 2 topics (vs naive 5-6): /nafy/status (state), /nafy/event (arrival/events)
- 3 services share 1 srv definition (NafyRequest.srv) -> 1 interface to maintain
- 1 node instead of 3 (was: navigation_node + queue_node + api_node)
- Reuses Nav2 action client; falls back to mock timer when Nav2 not running (Gazebo/real switch via param)
- Queue is in-memory deque, O(1) append/popleft, no extra DB/topic
"""

import json
import math
from collections import deque
from enum import Enum

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from std_msgs.msg import String
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose

from nafy_interfaces.srv import NafyRequest


# ---------- PLACES (placeholder, edit config/places.yaml) ----------
# In code fallback if yaml not loaded - you will update these after mapping
DEFAULT_PLACES = {
    "home":    {"x": 0.0, "y": 0.0, "yaw": 0.0},
    "office1": {"x": -12.1751, "y": 4.8504, "yaw": 1.5184},
    "office2": {"x": -14.3809, "y": 5.2972, "yaw": 1.5184},
    "office3": {"x": -19.367, "y": 6.4507, "yaw": 1.5184},
}
DOCTOR_TO_OFFICE = {
    "doctor1": "office1",
    "doctor2": "office2",
    "doctor3": "office3",
    # also allow direct office names
    "office1": "office1",
    "office2": "office2",
    "office3": "office3",
    "home": "home",
}

class State(Enum):
    IDLE_HOME = "IDLE_HOME"           # at home, waiting
    NAVIGATING = "NAVIGATING"         # going to office
    ARRIVED = "ARRIVED"               # at office waiting EndTask
    RETURNING = "RETURNING"           # going back home, interruptible


class NafyController(Node):
    def __init__(self):
        super().__init__("nafy_controller")

        # ---- params ----
        self.declare_parameter("mock_mode", True)
        self.declare_parameter("mock_duration", 4.0)
        self.declare_parameter("use_nav2", False)
        self.mock_mode = self.get_parameter("mock_mode").value
        self.mock_duration = self.get_parameter("mock_duration").value
        self.use_nav2 = self.get_parameter("use_nav2").value

        # Try load places.yaml if present (optional)
        self.places = DEFAULT_PLACES

        # ---- state ----
        self.state = State.IDLE_HOME
        self.current_target: str | None = None   # office name
        self.current_doctor: str | None = None
        self.queue: deque[str] = deque()         # queue of doctor_id
        self.nav_timer = None                    # mock navigation timer
        self.nav_goal_handle = None

        # ---- publishers (ONLY 2 topics) ----
        self.status_pub = self.create_publisher(String, "/nafy/status", 10)
        self.event_pub = self.create_publisher(String, "/nafy/event", 10)  # transient events: arrival, dispatch, etc.

        # ---- services (3 services, 1 srv type) ----
        self.srv_call = self.create_service(NafyRequest, "/nafy/call", self.handle_call)
        self.srv_reserve = self.create_service(NafyRequest, "/nafy/reserve", self.handle_reserve)
        self.srv_end = self.create_service(NafyRequest, "/nafy/end_task", self.handle_end_task)

        # ---- Nav2 action client (only if use_nav2) ----
        self.nav_client = None
        if self.use_nav2:
            self.nav_client = ActionClient(self, NavigateToPose, "navigate_to_pose")
            self.get_logger().info("Nav2 action client created (use_nav2=True)")

        # ---- status heartbeat 2 Hz ----
        self.create_timer(0.5, self.publish_status)

        self.get_logger().info("="*60)
        self.get_logger().info("🤖 NAFY CONTROLLER READY")
        self.get_logger().info(f" State={self.state.value} | mock={self.mock_mode} | use_nav2={self.use_nav2}")
        self.get_logger().info(f" Places: {list(self.places.keys())} -> {self.places}")
        self.get_logger().info(" Services: /nafy/call | /nafy/reserve | /nafy/end_task")
        self.get_logger().info(" Topics: /nafy/status | /nafy/event")
        self.get_logger().info("="*60)

    # ==================== HELPERS ====================
    def _office_for(self, doctor_id: str) -> str | None:
        return DOCTOR_TO_OFFICE.get(doctor_id.strip().lower())

    def _is_busy(self) -> bool:
        return self.state in (State.NAVIGATING, State.ARRIVED)

    def _can_call(self) -> bool:
        # Call allowed only when IDLE_HOME or RETURNING (per spec)
        return self.state in (State.IDLE_HOME, State.RETURNING)

    def _can_reserve(self) -> bool:
        return self.state in (State.NAVIGATING, State.ARRIVED)

    def _publish_event(self, event_type: str, target: str, extra: dict | None = None):
        payload = {"event": event_type, "target": target, "state": self.state.value}
        if self.current_doctor:
            payload["doctor"] = self.current_doctor
        if extra:
            payload.update(extra)
        msg = String(data=json.dumps(payload))
        self.event_pub.publish(msg)
        # Terminal log per spec: "send a command via the terminal indicating arrival"
        color = "\033[92m" if event_type == "arrived" else "\033[94m"
        reset = "\033[0m"
        self.get_logger().info(f"{color}[NAFY EVENT] {event_type.upper()} -> {target} | state={self.state.value}{reset}")
        print(f"{color}[NAFY TERMINAL] {event_type.upper()} at {target} | doctor={self.current_doctor} | queue={list(self.queue)}{reset}")

    def publish_status(self):
        """Single status topic replaces 3 separate topics (pose+queue+busy)"""
        payload = {
            "state": self.state.value,
            "current_target": self.current_target,
            "current_doctor": self.current_doctor,
            "queue": list(self.queue),
            "queue_length": len(self.queue),
            "can_call": self._can_call(),
            "can_reserve": self._can_reserve(),
            "can_end_task": self.state == State.ARRIVED,
            "is_busy": self._is_busy(),
            "places": self.places,  # app can show map
        }
        msg = String(data=json.dumps(payload))
        self.status_pub.publish(msg)

    def _make_pose(self, place_name: str) -> PoseStamped:
        p = self.places[place_name]
        pose = PoseStamped()
        pose.header.frame_id = "map"
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = float(p["x"])
        pose.pose.position.y = float(p["y"])
        pose.pose.position.z = 0.0
        # yaw -> quaternion
        yaw = float(p["yaw"])
        pose.pose.orientation.z = math.sin(yaw/2)
        pose.pose.orientation.w = math.cos(yaw/2)
        return pose

    # ==================== NAVIGATION ====================
    def navigate_to(self, target: str, doctor: str):
        """Start navigation to target. Cancels any existing goal."""
        self._cancel_navigation()
        self.current_target = target
        self.current_doctor = doctor

        if target == "home":
            self.state = State.RETURNING
        else:
            self.state = State.NAVIGATING

        self._publish_event("dispatch", target, {"doctor": doctor})

        if self.mock_mode or not self.use_nav2 or self.nav_client is None:
            # Mock navigation with timer
            self.get_logger().warn(f" MOCK navigating to {target} ({self.places[target]}) for {self.mock_duration}s")
            if self.nav_timer:
                self.nav_timer.cancel()
            self.nav_timer = self.create_timer(self.mock_duration, self._on_mock_arrival)
            # timer is periodic, we make it one-shot
            self._mock_target = target
        else:
            # Real Nav2
            if not self.nav_client.wait_for_server(timeout_sec=2.0):
                self.get_logger().error(" Nav2 server not available! Fallback to mock.")
                self.nav_timer = self.create_timer(self.mock_duration, self._on_mock_arrival)
                self._mock_target = target
                return
            goal = NavigateToPose.Goal()
            goal.pose = self._make_pose(target)
            self.get_logger().info(f" Nav2 goal sent: {target} -> {self.places[target]}")
            send_future = self.nav_client.send_goal_async(goal)
            send_future.add_done_callback(self._on_nav_goal_response)

    def _on_nav_goal_response(self, future):
        handle = future.result()
        if not handle.accepted:
            self.get_logger().error(" Nav2 goal rejected!")
            return
        self.nav_goal_handle = handle
        result_future = handle.get_result_async()
        result_future.add_done_callback(self._on_nav_result)

    def _on_nav_result(self, future):
        result = future.result()
        # status 4 = succeeded
        if result.status == 4:
            self._on_arrival(self.current_target)
        else:
            self.get_logger().warn(f" Navigation failed status={result.status}")

    def _on_mock_arrival(self):
        if self.nav_timer:
            self.nav_timer.cancel()
            self.nav_timer = None
        target = getattr(self, "_mock_target", self.current_target)
        self._on_arrival(target)

    def _on_arrival(self, target: str):
        if target == "home":
            self.state = State.IDLE_HOME
            self.current_target = None
            self.current_doctor = None
            self._publish_event("arrived_home", "home")
            self.get_logger().info("🏠 Nafy is HOME and IDLE")
            return
        # arrived at office
        self.state = State.ARRIVED
        self._publish_event("arrived", target)
        self.get_logger().info(f"✅ Nafy ARRIVED at {target} for {self.current_doctor} -> waiting EndTask")

    def _cancel_navigation(self):
        if self.nav_timer:
            self.nav_timer.cancel()
            self.nav_timer = None
        if self.nav_goal_handle:
            try:
                self.nav_goal_handle.cancel_goal_async()
            except Exception as e:
                self.get_logger().warn(f" cancel failed: {e}")
            self.nav_goal_handle = None

    # ==================== SERVICE HANDLERS ====================
    def handle_call(self, request, response):
        doctor = request.doctor_id.strip()
        office = self._office_for(doctor)
        self.get_logger().info(f"📞 CALL received: doctor={doctor} -> office={office} | state={self.state.value}")

        if not office or office == "home":
            response.success = False
            response.message = f"Unknown doctor '{doctor}'. Use doctor1/2/3"
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        if office in [DOCTOR_TO_OFFICE[d] for d in self.queue] or office == self.current_target:
            response.success = False
            response.message = f"{office} already queued or active"
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        # Check if call allowed
        if self.state == State.NAVIGATING or self.state == State.ARRIVED:
            response.success = False
            response.message = "Robot busy. CALL disabled, use RESERVE instead."
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        if self.state == State.IDLE_HOME:
            # direct dispatch
            self.navigate_to(office, doctor)
            response.success = True
            response.message = f"Dispatched to {office} for {doctor}"
        elif self.state == State.RETURNING:
            # INTERRUPT return-home -> go to new office (spec: must immediately interrupt)
            self.get_logger().warn(f" Interrupting RETURNING to serve {doctor} -> {office}")
            self.navigate_to(office, doctor)
            response.success = True
            response.message = f"Interrupted return-home, now heading to {office}"
        else:
            response.success = False
            response.message = f"Call not allowed in state {self.state.value}"

        response.state = self.state.value
        response.queue_json = json.dumps(list(self.queue))
        return response

    def handle_reserve(self, request, response):
        doctor = request.doctor_id.strip()
        office = self._office_for(doctor)
        self.get_logger().info(f"🔖 RESERVE received: doctor={doctor} -> {office} | state={self.state.value}")

        if not office or office == "home":
            response.success = False
            response.message = f"Unknown doctor '{doctor}'"
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        if not self._can_reserve():
            # Spec: reserve only when busy, but we also allow when returning? If returning, treat as call
            if self.state == State.RETURNING:
                response.success = False
                response.message = "Robot returning home, use CALL (it will interrupt)"
                response.state = self.state.value
                response.queue_json = json.dumps(list(self.queue))
                return response
            response.success = False
            response.message = f"Reserve not needed in state {self.state.value}. Use CALL."
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        if doctor in self.queue:
            response.success = False
            response.message = f"{doctor} already in queue at position {list(self.queue).index(doctor)+1}"
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        if doctor == self.current_doctor:
            response.success = False
            response.message = f"{doctor} is currently being served"
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        # FIFO: first fastest wins
        self.queue.append(doctor)
        self.get_logger().info(f" Queue updated: {list(self.queue)}")
        self._publish_event("reserved", office, {"queue": list(self.queue), "position": len(self.queue)})

        response.success = True
        response.message = f"Reserved {office} for {doctor}, position {len(self.queue)}"
        response.state = self.state.value
        response.queue_json = json.dumps(list(self.queue))
        return response

    def handle_end_task(self, request, response):
        doctor = request.doctor_id.strip()
        self.get_logger().info(f"✅ END_TASK received: doctor={doctor} | state={self.state.value} current={self.current_doctor}")

        if self.state != State.ARRIVED:
            response.success = False
            response.message = f"Not at office (state={self.state.value}), cannot end task"
            response.state = self.state.value
            response.queue_json = json.dumps(list(self.queue))
            return response

        # Optional: verify doctor matches current (allow any if mismatch but warn)
        if doctor != self.current_doctor and doctor.lower() not in ["any", "force"]:
            self.get_logger().warn(f" End task doctor mismatch: {doctor} vs {self.current_doctor} - proceeding anyway")

        self._publish_event("task_completed", self.current_target, {"doctor": self.current_doctor})

        # Next: check queue
        if len(self.queue) > 0:
            next_doctor = self.queue.popleft()
            next_office = self._office_for(next_doctor)
            self.get_logger().info(f" Dequeue next: {next_doctor} -> {next_office}, remaining {list(self.queue)}")
            self.navigate_to(next_office, next_doctor)
            response.success = True
            response.message = f"Task ended, now heading to {next_office} for {next_doctor}"
        else:
            # No more tasks -> return home
            self.get_logger().info(" No queue -> RETURNING HOME")
            self.navigate_to("home", "home")
            response.success = True
            response.message = "Task ended, returning home"

        response.state = self.state.value
        response.queue_json = json.dumps(list(self.queue))
        return response


def main(args=None):
    rclpy.init(args=args)
    node = NafyController()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()
