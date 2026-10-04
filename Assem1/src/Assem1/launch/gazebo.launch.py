import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, SetEnvironmentVariable
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    pkg_share = get_package_share_directory('Assem1')
    urdf_path = os.path.join(pkg_share, 'urdf', 'Assem1.urdf')
    rviz_config = os.path.join(pkg_share, 'rviz', 'display.rviz')

    with open(urdf_path, 'r') as f:
        robot_desc = f.read()

    gui_arg = DeclareLaunchArgument(
        'gui', default_value='true',
        description='Use joint_state_publisher_gui sliders')
    rviz_arg = DeclareLaunchArgument(
        'rviz', default_value='false',
        description='Also launch RViz2 alongside Gazebo')
    world_arg = DeclareLaunchArgument(
        'world', default_value='empty.sdf',
        description='Gz Sim world file (empty.sdf = empty world)')
    x_arg = DeclareLaunchArgument('x', default_value='0.0')
    y_arg = DeclareLaunchArgument('y', default_value='0.0')
    z_arg = DeclareLaunchArgument('z', default_value='0.5')
    yaw_arg = DeclareLaunchArgument('yaw', default_value='0.0')

    gui = LaunchConfiguration('gui')
    use_rviz = LaunchConfiguration('rviz')

    # Let Gz Sim resolve model://Assem1/meshes/... from this package's share dir.
    # model://Assem1/... is searched as <resource_path>/Assem1/..., so expose
    # the share/ parent (install/Assem1/share) plus existing env paths.
    pkg_parent = os.path.dirname(pkg_share)  # .../share
    gz_resource_path = (
        pkg_parent + ':' + os.environ.get('GZ_SIM_RESOURCE_PATH', '')
        if os.environ.get('GZ_SIM_RESOURCE_PATH', '')
        else pkg_parent
    )
    set_gz_resource = SetEnvironmentVariable(
        'GZ_SIM_RESOURCE_PATH', gz_resource_path)

    # Empty world in Gz Sim 8 (Harmonic)
    gz_sim = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory('ros_gz_sim'),
                'launch', 'gz_sim.launch.py')),
        launch_arguments={
            'gz_args': [LaunchConfiguration('world'), ' -r'],
        }.items(),
    )

    robot_state_pub = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        name='robot_state_publisher',
        output='screen',
        parameters=[
            {'robot_description': robot_desc},
            {'use_sim_time': True},
        ],
    )

    jsp_gui = Node(
        package='joint_state_publisher_gui',
        executable='joint_state_publisher_gui',
        name='joint_state_publisher_gui',
        output='screen',
        condition=IfCondition(gui),
    )

    # Spawn URDF straight into Gz Sim (sdformat converts URDF internally)
    spawn = Node(
        package='ros_gz_sim',
        executable='create',
        name='spawn_assem1',
        output='screen',
        arguments=[
            '-file', urdf_path,
            '-name', 'Assem1',
            '-x', LaunchConfiguration('x'),
            '-y', LaunchConfiguration('y'),
            '-z', LaunchConfiguration('z'),
            '-Y', LaunchConfiguration('yaw'),
        ],
    )

    # Sim clock -> ROS
    clock_bridge = Node(
        package='ros_gz_bridge',
        executable='parameter_bridge',
        name='clock_bridge',
        output='screen',
        arguments=['/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock'],
    )

    rviz = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config],
        condition=IfCondition(use_rviz),
    )

    return LaunchDescription([
        gui_arg, rviz_arg, world_arg, x_arg, y_arg, z_arg, yaw_arg,
        gz_sim, robot_state_pub, jsp_gui, spawn, clock_bridge, rviz,
    ])
