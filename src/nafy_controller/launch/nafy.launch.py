from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('nafy_controller')
    config = os.path.join(pkg_share, 'config', 'places.yaml')

    mock_arg = DeclareLaunchArgument('mock_mode', default_value='true')
    nav2_arg = DeclareLaunchArgument('use_nav2', default_value='false')

    controller = Node(
        package='nafy_controller',
        executable='controller',
        name='nafy_controller',
        parameters=[config, {
            'mock_mode': LaunchConfiguration('mock_mode'),
            'use_nav2': LaunchConfiguration('use_nav2'),
            'mock_duration': 4.0,
        }],
        output='screen',
        emulate_tty=True,
    )

    return LaunchDescription([mock_arg, nav2_arg, controller])
