cmake_minimum_required(VERSION 3.8)
project(Assem1)

find_package(ament_cmake REQUIRED)

install(
  DIRECTORY config launch meshes urdf textures rviz
  DESTINATION share/${PROJECT_NAME}
)

ament_package()
