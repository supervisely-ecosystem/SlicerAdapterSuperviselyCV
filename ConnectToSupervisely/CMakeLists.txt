#-----------------------------------------------------------------------------
set(MODULE_NAME ConnectToSupervisely)

#-----------------------------------------------------------------------------
set(MODULE_PYTHON_SCRIPTS
  labelingJobsAnnotating.py
  labelingJobsReviewing.py
  )

set(RESOURCES_FILES
  Resources/Icons/accepted.svg
  Resources/Icons/done.svg
  Resources/Icons/label.svg   
  Resources/Icons/labelingJobsAnnotating.png
  Resources/Icons/labelingJobsReviewing.png
  Resources/Icons/none.svg 
  Resources/Icons/rejected.svg
  Resources/Icons/supervisely.svg
  Resources/UI/labelingJobsAnnotating.ui
  Resources/UI/labelingJobsReviewing.ui  
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
