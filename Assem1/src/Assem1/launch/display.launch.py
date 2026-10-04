import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.conditions import IfCondition, UnlessCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_description_path():
    pkg = get_package_share_directory('Assem1')
    return os.path.join(pkg, 'urdf', 'Assem1.urdf')


def generate_launch_description():
    pkg_share = get_package_share_directory('Assem1')
    urdf_path = os.path.join(pkg_share, 'urdf', 'Assem1.urdf')
    rviz_config = os.path.join(pkg_share, 'rviz', 'display.rviz')

    with open(urdf_path, 'r') as f:
        robot_desc = f.read()

    gui_arg = DeclareLaunchArgument(
        'gui', default_value='true',
        description='Use joint_state_publisher_gui sliders (true) or plain joint_state_publisher (false)')
    rviz_arg = DeclareLaunchArgument(
        'rviz', default_value='true',
        description='Launch RViz2')

    gui = LaunchConfiguration('gui')
    use_rviz = LaunchConfiguration('rviz')

    robot_state_pub = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[{'robot_description': robot_desc}],
    )

    # Slider window for continuous joints joint_1..joint_6
    jsp_gui = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen',
        condition=IfCondition(gui),
    )

    jsp = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        output='screen',
        condition=UnlessCondition(gui),
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config],
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription([gui_arg, rviz_arg, robot_state_pub, jsp_gui, jsp, rviz])
