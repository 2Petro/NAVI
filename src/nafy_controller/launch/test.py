import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource

def generate_launch_description():
    pkg_nafy = get_package_share_directory('nafy_controller')
    ros_gz_sim = get_package_share_directory('ros_gz_sim')
    tb3_gazebo = get_package_share_directory('turtlebot3_gazebo')

    world = os.path.join(pkg_nafy, 'worlds', 'HTIFULL.sdf')

    gzserver = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': f'-r -s -v1 {world}', 'on_exit_shutdown': 'true'}.items()
    )
    gzclient = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': '-g -v1', 'on_exit_shutdown': 'true'}.items()
    )
    # Spawn Waffle custom at home -36.7,8.87 with 10m lidar (from src/nafy_controller/models/waffle_custom)
    from launch_ros.actions import Node
    custom_waffle_sdf = os.path.join(pkg_nafy, 'models', 'waffle_custom', 'model.sdf')
    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=['-name', 'waffle', '-file', custom_waffle_sdf, '-x', '39.29', '-y', '-9.70', '-z', '0.01'],
        output='screen',
    )
    # Bridge for custom waffle (same as turtlebot3_waffle_bridge.yaml)
    bridge_params = os.path.join(tb3_gazebo, 'params', 'turtlebot3_waffle_bridge.yaml')
    bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        arguments=['--ros-args', '-p', f'config_file:={bridge_params}'],
        output='screen',
    )
    image_bridge = Node(
        package='ros_gz_image',
        executable='image_bridge',
        arguments=['/camera/image_raw'],
        output='screen',
    )
    rsp = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(tb3_gazebo, 'launch', 'robot_state_publisher.launch.py')),
        launch_arguments={'use_sim_time': 'true'}.items()
    )

    # Ensure gz can find turtlebot models + custom
    from launch.actions import AppendEnvironmentVariable
    set_path = AppendEnvironmentVariable('GZ_SIM_RESOURCE_PATH', [os.path.join(pkg_nafy, 'models'), ':', os.path.join(tb3_gazebo, 'models')])

    ld = LaunchDescription()
    ld.add_action(set_path)
    ld.add_action(gzserver)
    ld.add_action(gzclient)
    ld.add_action(spawn)
    ld.add_action(bridge)
    ld.add_action(image_bridge)
    ld.add_action(rsp)
    return ld
