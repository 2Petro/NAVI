#!/bin/bash
# LunchNafy.sh - HTI stack: Gazebo (Assem1) + Nav2 (SLAM map) + RViz
# Matches current project state (Oct 2026):
#  - robot: models/assem1 (Assem1, A1M8 + D435i) spawned by hti_gazebo.launch.py
#  - default map: src/nafy_controller/maps/HTIFULL_SLAMP.yaml
#  - params: src/nafy_controller/config/nav2_waffle.yaml (robot_radius 0.4779, lidar min 0.4975)

source /opt/ros/jazzy/setup.bash
source /root/ros2_ws/install/setup.bash

export TURTLEBOT3_MODEL=waffle

echo "======================================"
echo " Starting HTI ROS2 stack"
echo "======================================"

# -------------------------
# 0. Clean previous runs (single stack only - dual stacks break lifecycle bonds)
# -------------------------
echo "-- cleaning previous runs --"
pkill -f "component_container_isolated" 2>/dev/null
pkill -f "gz sim" 2>/dev/null
pkill -f "parameter_bridge" 2>/dev/null
pkill -f "image_bridge" 2>/dev/null
pkill -f "robot_state_publisher" 2>/dev/null
pkill -f "rviz2" 2>/dev/null
sleep 5

wait_for_topic() {
    # $1 = topic, $2 = timeout seconds
    local TOPIC="$1" TIMEOUT="$2" i
    for i in $(seq 1 "$TIMEOUT"); do
        timeout 5 ros2 topic echo "$TOPIC" --once >/dev/null 2>&1 && return 0
        sleep 1
    done
    echo "TIMEOUT waiting for $TOPIC"
    return 1
}

# -------------------------
# Gazebo
# -------------------------
echo "-- launching Gazebo (Assem1 in HTIFULL world) --"
ros2 launch nafy_controller hti_gazebo.launch.py &
GAZEBO_PID=$!

echo "-- waiting for /scan (sensors up) --"
wait_for_topic /scan 150 || exit 1
echo "-- Gazebo OK --"

# -------------------------
# Nav2 (default SLAM map from project maps/)
# -------------------------
echo "-- launching Nav2 --"
ros2 launch nav2_bringup bringup_launch.py \
    map:=/root/ros2_ws/src/nafy_controller/maps/HTIFULL_SLAMP.yaml \
    params_file:=/root/ros2_ws/src/nafy_controller/config/nav2_waffle.yaml \
    use_sim_time:=true \
    autostart:=true &
NAV2_PID=$!

echo "-- waiting for /map (localization active) --"
wait_for_topic /map 180 || exit 1
echo "-- waiting for navigation tail (controller/bt/planner) --"
sleep 30
echo "-- Nav2 OK --"

# -------------------------
# RViz
# -------------------------
echo "-- launching RViz (sim time, so image/TF filters match Gazebo clock) --"
rviz2 -d /opt/ros/jazzy/share/nav2_bringup/rviz/nav2_default_view.rviz --ros-args -p use_sim_time:=true &
RVIZ_PID=$!

sleep 5

echo
echo "======================================"
echo " TOP-LEVEL PIDs"
echo "======================================"
echo "Gazebo launch : $GAZEBO_PID"
echo "Nav2 launch   : $NAV2_PID"
echo "RViz          : $RVIZ_PID"

echo
echo "======================================"
echo " COMPLETE PROCESS TREES"
echo "======================================"

show_tree() {
    local PID="$1"
    local LEVEL="$2"

    kill -0 "$PID" 2>/dev/null || return

    ps -p "$PID" \
        -o pid=,ppid=,pgid=,sid=,stat=,args= \
        2>/dev/null |
        sed "s/^/$(printf '%*s' "$LEVEL" '')/"

    local CHILDREN
    CHILDREN=$(pgrep -P "$PID" 2>/dev/null || true)

    for CHILD in $CHILDREN; do
        show_tree "$CHILD" $((LEVEL + 2))
    done

}

echo
echo "----- GAZEBO -----"
show_tree "$GAZEBO_PID" 2

echo
echo "----- NAV2 -----"
show_tree "$NAV2_PID" 2

echo
echo "----- RVIZ -----"
show_tree "$RVIZ_PID" 2

echo
echo "======================================"
echo " All stacks running."
echo " Press Ctrl+C to stop this launcher."
echo "======================================"

wait
