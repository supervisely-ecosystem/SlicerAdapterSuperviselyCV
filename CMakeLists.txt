cmake_minimum_required(VERSION 3.16.3...3.19.7 FATAL_ERROR)

project(ConnectToSupervisely)

#-----------------------------------------------------------------------------
# Extension meta-information
set(EXTENSION_HOMEPAGE "https://github.com/supervisely-ecosystem/SlicerConnectToSupervisely")
set(EXTENSION_CATEGORY "Supervisely")
set(EXTENSION_CONTRIBUTORS "Siarhei Sych (Supervisely)")
set(EXTENSION_DESCRIPTION "This extension provides seamless integration between the 3D Slicer and Supervisely Computer Vision platform, empowering users to efficiently work with Labeling Jobs directly within the familiar 3D Slicer environment. Users can harness the full power of 3D visualization and annotation tools to enhance the labeling process for volumetric data, streamline annotation creation, and facilitate reviews. https://supervisely.com/")
set(EXTENSION_ICONURL "https://raw.githubusercontent.com/supervisely-ecosystem/SlicerConnectToSupervisely/master/Images/icon_png_128x128.png")
set(EXTENSION_SCREENSHOTURLS "https://raw.githubusercontent.com/supervisely-ecosystem/SlicerConnectToSupervisely/master/Images/annotation_process_slicer.png")
set(EXTENSION_DEPENDS "NA") # Specified as a list or "NA" if no dependencies


#-----------------------------------------------------------------------------
# Extension dependencies
find_package(Slicer REQUIRED)
include(${Slicer_USE_FILE})

#-----------------------------------------------------------------------------
# Extension modules
## NEXT_MODULE
add_subdirectory(ConnectToSupervisely)

#-----------------------------------------------------------------------------
include(${Slicer_EXTENSION_GENERATE_CONFIG})
include(${Slicer_EXTENSION_CPACK})

