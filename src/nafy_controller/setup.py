from setuptools import find_packages, setup

package_name = 'nafy_controller'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/nafy.launch.py']),
        ('share/' + package_name + '/config', ['config/places.yaml']),
        ('share/' + package_name + '/worlds', ['worlds/HTIFULL.sdf', 'worlds/HTIFULL.world', 'worlds/HTIFULL.yaml', 'worlds/HTIFULL.pgm']),
        ('share/' + package_name + '/worlds', ['worlds/HTIFULL.stl']),
        ('share/' + package_name + '/models/waffle_custom', ['models/waffle_custom/model.sdf', 'models/waffle_custom/model.config', 'models/waffle_custom/model-1_4.sdf']),
        ('share/' + package_name + '/models/assem1', ['models/assem1/model.sdf', 'models/assem1/model.config']),
        ('share/' + package_name + '/config', ['config/nav2_waffle.yaml', 'config/places.yaml']),
        ('share/' + package_name + '/launch', ['launch/hti_gazebo.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Nafy Team',
    maintainer_email='nafy@hospital.local',
    description='Optimized Nafy dispatch controller - hospital robot API',
    license='MIT',
    extras_require={
        'test': ['pytest'],
    },
    entry_points={
        'console_scripts': [
            'controller = nafy_controller.controller:main',
            'test_client = nafy_controller.test_client:main',
        ],
    },
)
