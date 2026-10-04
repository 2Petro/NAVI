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
        launch_arguments={'gz_args': f'-r -s -v2 {world}', 'on_exit_shutdown': 'true'}.items()
    )
    gzclient = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(ros_gz_sim, 'launch', 'gz_sim.launch.py')),
        launch_arguments={'gz_args': '-g -v2', 'on_exit_shutdown': 'true'}.items()
    )
    # Spawn Assem1 at home 39.29,-9.70 with A1M8 lidar + D435i (from src/nafy_controller/models/assem1)
    from launch_ros.actions import Node
    assem1_sdf = os.path.join(pkg_nafy, 'models', 'assem1', 'model.sdf')
    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        arguments=['-name', 'assem1', '-file', assem1_sdf, '-x', '39.29', '-y', '-9.70', '-z', '1'],
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
    depth_bridge = Node(
        package='ros_gz_image',
        executable='image_bridge',
        arguments=['/camera/depth_image'],
        output='screen',
    )
    # Robot state publisher for Assem1 (URDF from THIS workspace install - deterministic, ignores other workspaces)
    assem1_share = os.path.join(os.path.dirname(pkg_nafy), 'Assem1')
    with open(os.path.join(assem1_share, 'urdf', 'Assem1.urdf'), 'r') as f:
        assem1_desc = f.read()
    rsp = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        parameters=[{'robot_description': assem1_desc, 'use_sim_time': True}],
        output='screen',
    )

    # Ensure gz can find turtlebot models + custom + Assem1 (model://Assem1 -> install/share/Assem1)
    from launch.actions import AppendEnvironmentVariable
    set_path = AppendEnvironmentVariable('GZ_SIM_RESOURCE_PATH', [os.path.join(pkg_nafy, 'models'), ':', os.path.join(tb3_gazebo, 'models'), ':', os.path.dirname(pkg_nafy)])

    ld = LaunchDescription()
    ld.add_action(set_path)
    ld.add_action(gzserver)
    ld.add_action(gzclient)
    ld.add_action(spawn)
    ld.add_action(bridge)
    ld.add_action(image_bridge)
    ld.add_action(depth_bridge)
    ld.add_action(rsp)
    return ld
