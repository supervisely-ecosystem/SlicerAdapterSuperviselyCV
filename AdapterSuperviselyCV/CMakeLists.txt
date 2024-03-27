#-----------------------------------------------------------------------------
set(MODULE_NAME AdapterSuperviselyCV)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  labelingJobsAnnotation.py
  labelingJobsReview.py
  )

set(RESOURCES_FILES
  Resources/Icons/done.svg
  Resources/Icons/label.svg
  Resources/Icons/none.svg
  Resources/Icons/accepted.svg
  Resources/Icons/rejected.svg
  Resources/Icons/labelingJobsAnnotation.png
  Resources/Icons/labelingJobsReview.png
  Resources/UI/labelingJobsAnnotation.ui
  Resources/UI/labelingJobsReview.ui
  )

set(MODULE_LIB
  moduleLib/__init__.py
  moduleLib/segmentation.py
  moduleLib/ui.py
  moduleLib/utils.py
  )

set(MODULE_PYTHON_RESOURCES
  ${RESOURCES_FILES}
  ${MODULE_LIB}
  )
  
#-----------------------------------------------------------------------------
slicerMacroBuildScriptedModule(
  NAME ${MODULE_NAME}
  SCRIPTS ${MODULE_PYTHON_SCRIPTS}
  RESOURCES ${MODULE_PYTHON_RESOURCES}
  )
