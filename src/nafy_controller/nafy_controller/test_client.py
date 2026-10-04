#!/usr/bin/env python3
"""
Test client to simulate mobile app: 3 doctors pressing Call/Reserve/EndTask
Usage:
  ros2 run nafy_controller test_client -- --scenario 1
Scenarios:
  1: Basic flow: doctor1 calls, doctor2 reserves, doctor1 ends -> doctor2 served -> home
  2: Interrupt return-home: finish all -> returning -> doctor3 calls interrupts
  3: Stress: concurrent calls
"""
import argparse
import json
import sys
import time
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from nafy_interfaces.srv import NafyRequest

class TestClient(Node):
    def __init__(self):
        super().__init__("nafy_test_client")
        self.cli_call = self.create_client(NafyRequest, "/nafy/call")
        self.cli_reserve = self.create_client(NafyRequest, "/nafy/reserve")
        self.cli_end = self.create_client(NafyRequest, "/nafy/end_task")
        self.create_subscription(String, "/nafy/status", self.on_status, 10)
        self.create_subscription(String, "/nafy/event", self.on_event, 10)
        self.last_status = {}

    def on_status(self, msg):
        try:
            self.last_status = json.loads(msg.data)
        except: pass

    def on_event(self, msg):
        self.get_logger().info(f"\033[93m[EVENT] {msg.data}\033[0m")

    def wait_service(self):
        for cli, name in [(self.cli_call,"call"),(self.cli_reserve,"reserve"),(self.cli_end,"end_task")]:
            if not cli.wait_for_service(timeout_sec=5.0):
                self.get_logger().error(f"Service /nafy/{name} not available")
                return False
        return True

    async def call(self, doctor):
        req = NafyRequest.Request(doctor_id=doctor)
        res = await self.cli_call.call_async(req)
        print(f" CALL {doctor} -> success={res.success} | {res.message} | state={res.state} queue={res.queue_json}")
        return res

    async def reserve(self, doctor):
        req = NafyRequest.Request(doctor_id=doctor)
        res = await self.cli_reserve.call_async(req)
        print(f" RESERVE {doctor} -> success={res.success} | {res.message} | queue={res.queue_json}")
        return res

    async def end_task(self, doctor):
        req = NafyRequest.Request(doctor_id=doctor)
        res = await self.cli_end.call_async(req)
        print(f" END_TASK {doctor} -> success={res.success} | {res.message} | state={res.state}")
        return res

async def run_scenario(node: TestClient, scenario: int):
    assert node.wait_service()
    print(f"\n{'='*60}\n SCENARIO {scenario}\n{'='*60}")
    if scenario == 1:
        print("doctor1 calls -> doctor2+3 reserve -> doctor1 ends -> auto to doctor2 -> ends -> doctor3 -> home")
        await node.call("doctor1")
        time.sleep(1)
        await node.reserve("doctor2")
        await node.reserve("doctor3")
        # try duplicate reserve
        await node.reserve("doctor2")
        # try call when busy (should fail)
        await node.call("doctor3")
        print(" -- waiting for arrival (mock 4s) --")
        time.sleep(5)
        await node.end_task("doctor1")
        time.sleep(6)  # travel to doctor2
        await node.end_task("doctor2")
        time.sleep(6)
        await node.end_task("doctor3")
        time.sleep(6)  # return home
        print(f" Final status: {node.last_status}")

    elif scenario == 2:
        print("Interrupt return-home: finish -> returning -> doctor3 calls")
        await node.call("doctor1")
        time.sleep(5)
        await node.end_task("doctor1")
        print(" -- returning home now, interrupt after 1s --")
        time.sleep(1.5)
        await node.call("doctor3")  # should interrupt
        time.sleep(5)
        await node.end_task("doctor3")
        time.sleep(5)
        print(f" Final: {node.last_status}")

    elif scenario == 3:
        print("Race: 3 doctors call at same time")
        import asyncio
        results = await asyncio.gather(node.call("doctor1"), node.call("doctor2"), node.call("doctor3"))
        print(results)
        time.sleep(5)
        await node.end_task("doctor1")
        time.sleep(5)
        await node.reserve("doctor2")  # should queue now
        time.sleep(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", type=int, default=1)
    args, _ = parser.parse_known_args()

    rclpy.init()
    node = TestClient()
    # spin in background thread?
    import threading
    spin_thread = threading.Thread(target=lambda: rclpy.spin(node), daemon=True)
    spin_thread.start()
    time.sleep(1)  # wait for connection

    import asyncio
    # need to run async via rclpy executor? Use simple loop
    async def runner():
        await run_scenario(node, args.scenario)

    # Use node's executor to run? fallback to synchronous with time.sleep and futures
    # For simplicity, use blocking calls with while not future.done()
    # We'll re-implement sync version
    def sync_call(doctor):
        req = NafyRequest.Request(doctor_id=doctor)
        fut = node.cli_call.call_async(req)
        rclpy.spin_until_future_complete(node, fut, timeout_sec=3)
        res = fut.result()
        print(f" CALL {doctor} -> {res.success} | {res.message} | {res.state}")
        return res
    def sync_reserve(doctor):
        req = NafyRequest.Request(doctor_id=doctor)
        fut = node.cli_reserve.call_async(req)
        rclpy.spin_until_future_complete(node, fut, timeout_sec=3)
        res = fut.result()
        print(f" RESERVE {doctor} -> {res.success} | {res.message}")
        return res
    def sync_end(doctor):
        req = NafyRequest.Request(doctor_id=doctor)
        fut = node.cli_end.call_async(req)
        rclpy.spin_until_future_complete(node, fut, timeout_sec=3)
        res = fut.result()
        print(f" END {doctor} -> {res.success} | {res.message} | {res.state}")
        return res

    if args.scenario == 1:
        print("\n=== SCENARIO 1: Full queue flow ===")
        sync_call("doctor1")
        time.sleep(0.5)
        sync_reserve("doctor2")
        sync_reserve("doctor3")
        sync_reserve("doctor2")  # duplicate
        sync_call("doctor3")     # should fail (busy)
        print(" -- waiting arrival 5s --")
        time.sleep(5)
        sync_end("doctor1")
        time.sleep(5)
        sync_end("doctor2")
        time.sleep(5)
        sync_end("doctor3")
        time.sleep(5)
        print(f"Final status: {node.last_status}")
    elif args.scenario == 2:
        print("\n=== SCENARIO 2: Interrupt return ===")
        sync_call("doctor1")
        time.sleep(5)
        sync_end("doctor1")
        print(" -- returning, interrupt in 1s --")
        time.sleep(1.5)
        sync_call("doctor3")
        time.sleep(5)
        sync_end("doctor3")
        time.sleep(5)
        print(f"Final: {node.last_status}")

    node.destroy_node()
    rclpy.shutdown()

if __name__ == "__main__":
    main()
