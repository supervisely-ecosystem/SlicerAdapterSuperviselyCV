import copy
import logging
import os
from functools import partial
from json import load
from pathlib import Path
from typing import Literal

import qt
import requests
import slicer
import vtk
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import *

try:
    import supervisely as sly
    from supervisely.api.labeling_job_api import LabelingJobInfo

    import dotenv  # isort:skip
except ModuleNotFoundError:
    pass


from moduleLib import (
    InputDialog,
    block_widget,
    check_and_restore_libraries,
    import_supervisely,
    log_method_call,
    log_method_call_args,
    segmentClass,
    volumeClass,
)

# --------------------------------------- Global Variables --------------------------------------- #

ENV_FILE_PATH = os.path.join(Path.home(), "supervisely_slicer.env")
DEFAULT_WORK_DIR = os.path.join(Path.home(), "supervisely_slicer_data")


# -------------------------------------- LabelingJobsReview -------------------------------------- #


class labelingJobsReview(ScriptedLoadableModule):
    """Uses ScriptedLoadableModule base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Supervisely Labeling Jobs Reviewing")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Supervisely")]
        self.parent.dependencies = []
        self.parent.contributors = []
        # _() function marks text as translatable to other languages
        self.parent.helpText = _(
            """
This extension module designed to organize and manage the work of labeling teams on the <a href='https://supervisely.com/'>Supervisely</a> computer vision platform.
Allows reviewers to make changes to annotations, accept or reject the work done by annotators, and restart or complete Labeling Jobs.
More information about the module can be found in the <a href='https://github.com/supervisely-ecosystem/SlicerConnectToSupervisely/blob/master/README.md'>documentation</a>.
"""
        )
        self.parent.acknowledgementText = _(
            """
This extension module has been developed by <a href='https://www.linkedin.com/in/s-sych/'>Siarhei Sych</a> (<a href='https://supervisely.com/'>Supervisely</a>).
It is based on a scripted module template originally developed by Jean-Christophe Fillion-Robin, Kitware Inc., Andras Lasso, PerkLab,
and Steve Pieper, Isomics, Inc. and was partially funded by NIH grant 3P41RR013218-12S1.
"""
        )


# ----------------------------------- LabelingJobsReviewWidget ----------------------------------- #


class labelingJobsReviewWidget(ScriptedLoadableModuleWidget):
    """Uses ScriptedLoadableModuleWidget base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, parent=None) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.__init__(self, parent)
        self.logic = None
        self.ready_to_start = False

    def setup(self) -> None:
        """Called when the user opens the module the first time and the widget is initialized."""
        ScriptedLoadableModuleWidget.setup(self)

        # Check if packages are reinstalled with another versions during the Supervisely module installation and ask user to restore them if needed.
        # Supervisely package will be uninstalled if you confirm restoring the previous versions.
        check_and_restore_libraries()

        # Set self.ready_to_start = True if supervisely module is imported successfully.
        import_supervisely(self)

        # If supervisely module is not imported successfully, block the widget.
        if not self.ready_to_start:
            block_widget(self)
            return

        if not os.path.exists(ENV_FILE_PATH):
            with open(ENV_FILE_PATH, "w") as f:
                f.write("")
            dotenv.set_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE", f"{self.moduleName}")
            dotenv.set_key(ENV_FILE_PATH, "WORKING_DIR", DEFAULT_WORK_DIR)

        # Load widget from .ui file (created by Qt Designer).
        # Additional widgets can be instantiated manually and added to self.layout.
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/labelingJobsReview.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = labelingJobsReviewLogic(self.ui)

        # Configure default UI state
        self.logic.configureUI()

        # Buttons
        self.ui.connectButton.connect("clicked(bool)", self.onConnectButton)
        self.ui.RefreshJobs.connect("clicked(bool)", self.onRefreshJobsButton)
        self.ui.startJobButton.connect("clicked(bool)", self.onStartJobButton)
        self.ui.saveButton.connect("clicked(bool)", self.onSaveButton)
        self.ui.acceptButton.connect("clicked(bool)", self.onAcceptButton)
        self.ui.rejectButton.connect("clicked(bool)", self.onRejectButton)
        self.ui.restartButton.connect("clicked(bool)", self.onRestartButton)
        self.ui.finishButton.connect("clicked(bool)", self.onFinishButton)
        self.ui.workingDirButton.directoryChanged.connect(self.onWorkingDirButton)

        # Lists
        self.ui.teamSelector.currentIndexChanged.connect(self.onSelectTeam)
        self.ui.jobSelector.currentIndexChanged.connect(self.onSelectJob)
        # self.ui.jobSelector.currentTextChanged.connect(self.onSelectJob)
        self.ui.volumeSelector.currentIndexChanged.connect(self.onSelectVolume)

        # Checkboxes
        self.ui.skipSegmentStatusCheck.connect("clicked(bool)", self.onTickSkipSegmentStatus)

    def enter(self) -> None:
        """Called each time the user opens this module."""
        if self.ready_to_start:
            slicer.util.setDataProbeVisible(False)
            activeModule = dotenv.get_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE")
            if not activeModule:
                dotenv.set_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE", f"{self.moduleName}")
            elif activeModule != self.moduleName:
                slicer.mrmlScene.Clear()
                slicer.util.reloadScriptedModule(activeModule)
                dotenv.set_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE", f"{self.moduleName}")

    def exit(self) -> None:
        """Called each time the user opens a different module."""
        slicer.util.setDataProbeVisible(True)

    @log_method_call
    def onConnectButton(self) -> None:
        """Run processing when user clicks "Connect" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to authenticate."), waitCursor=True):
            self.logic.logIn()
            self.ui.workingDirButton.setEnabled(True)

    @log_method_call
    def onSelectTeam(self) -> None:
        """Run processing when user change "Team" in selector."""
        with slicer.util.tryWithErrorDisplay(_("Failed to select Team."), waitCursor=True):
            index = self.ui.teamSelector.findText("Select...")
            self.ui.teamSelector.removeItem(index)
            if self.logic.savePath and os.path.exists(self.logic.savePath):
                if self.logic.volume and slicer.util.confirmYesNoDisplay(
                    "Do you want to save changes before select another team?"
                ):
                    self.logic.saveAnnotations()
                    self.logic.uploadAnnObjectChangesToServer()
                    self.logic.uploadTagsChangesToServer()
            self.logic.removeAnnotaionsFromScene()
            self.logic.removeVolumeFromScene()
            self.logic.removeLocalData()
            if self.logic.volume:
                self.logic.volume.clear()
                self.logic.volume = None
            self.logic.getJobs()
            self.ui.workingDirButton.setEnabled(True)
            self.ui.activeJob.setChecked(False)
            self.ui.activeJob.setEnabled(False)

    @log_method_call
    def onSelectJob(self) -> None:
        """Run processing when user change "Job" in selector."""
        with slicer.util.tryWithErrorDisplay(_("Failed to select Job."), waitCursor=True):
            index = self.ui.jobSelector.findText("Select...")
            self.ui.jobSelector.removeItem(index)
            if self.logic.savePath and os.path.exists(self.logic.savePath):
                if self.logic.volume and slicer.util.confirmYesNoDisplay(
                    "Do you want to save changes before select another job?"
                ):
                    self.logic.saveAnnotations()
                    self.logic.uploadAnnObjectChangesToServer()
                    self.logic.uploadTagsChangesToServer()
            self.logic.removeAnnotaionsFromScene()
            self.logic.removeVolumeFromScene()
            self.logic.removeLocalData()
            if self.logic.volume:
                self.logic.volume.clear()
                self.logic.volume = None
            self.logic.changeLabelingButtonState()
            self.logic.setActiveJob()
            self.ui.tags.setEnabled(False)
            self.ui.tags.setChecked(False)
            self.ui.workingDirButton.setEnabled(True)

    @log_method_call
    def onRefreshJobsButton(self) -> None:
        """Run processing when user clicks "Refresh Jobs List" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to refresh Jobs list."), waitCursor=True):
            self.logic.getJobs(refresh=True)

    @log_method_call
    def onStartJobButton(self) -> None:
        """Run processing when user clicks "Start labeling" button."""
        with slicer.util.tryWithErrorDisplay(
            _("Failed to download project data."), waitCursor=True
        ):
            if self.logic.volume:
                self.logic.volume.clear()
                self.logic.volume = None
            self.logic.downloadData()
            # self.logic.changeJobStatus("on_review")
            self.ui.workingDirButton.setEnabled(False)
            self.logic.fulfillInfo()

    @log_method_call
    def onSelectVolume(self) -> None:
        """Run processing when user clicks "Apply" button."""
        with slicer.util.tryWithErrorDisplay(
            _("Failed to load volumes with annotations."), waitCursor=True
        ):
            index = self.ui.volumeSelector.findText("Select...")
            self.ui.volumeSelector.removeItem(index)
            if (
                self.ui.autoSaveVolume.isChecked()
                and self.logic.volume
                and self.logic.volume.segmentations
            ):
                self.logic.saveAnnotations()
                self.logic.uploadAnnObjectChangesToServer()
                self.logic.uploadTagsChangesToServer()
            try:
                self.logic.loadVolumes()
            except Exception as e:
                self.logic.removeAnnotaionsFromScene()
                self.logic.removeVolumeFromScene()
                # self.logic.removeLocalData()
                if self.logic.volume:
                    self.logic.volume.clear()
                    self.logic.volume = None
                raise e

    @log_method_call
    def onSaveButton(self) -> None:
        """Run processing when user clicks "Confirm changes" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to save data."), waitCursor=True):
            self.logic.saveAnnotations()
            self.logic.uploadAnnObjectChangesToServer()
            self.logic.uploadTagsChangesToServer()

    @log_method_call
    def onAcceptButton(self) -> None:
        """Run processing when user clicks "Confirm changes" button."""
        with slicer.util.tryWithErrorDisplay(
            _('Failed to set status "accepted".'), waitCursor=True
        ):
            self.logic.saveAnnotations()
            self.logic.uploadAnnObjectChangesToServer()
            self.logic.uploadTagsChangesToServer()
            self.logic.changeVolumeStatus(status="accepted")
            self.logic.setVolumeStatusUI()

    @log_method_call
    def onRejectButton(self) -> None:
        """Run processing when user clicks "Confirm changes" button."""
        with slicer.util.tryWithErrorDisplay(
            _('Failed to set status "rejected".'), waitCursor=True
        ):
            self.logic.saveAnnotations()
            self.logic.uploadAnnObjectChangesToServer()
            self.logic.uploadTagsChangesToServer()
            self.logic.changeVolumeStatus(status="rejected")
            self.logic.setVolumeStatusUI()

    @log_method_call
    def onFinishButton(self) -> None:
        """Run processing when user clicks "Submit" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to Finished job."), waitCursor=True):
            self.logic.changeJobStatus("completed")
            slicer.mrmlScene.Clear()
            self.logic.removeLocalData()
            if self.logic.volume:
                self.logic.volume.clear()
                self.logic.volume = None
            self.logic.getJobs()

    @log_method_call
    def onRestartButton(self) -> None:
        """Run processing when user clicks "Submit" button."""
        with slicer.util.tryWithErrorDisplay(_("Failed to Restart job."), waitCursor=True):
            if self.ui.restartRejected.isChecked():
                message = """
A new job will be created with volumes marked as Rejected only.

Do you want to continue?"""
            else:
                message = """
A new job will be created with the unmarked volumes and volumes marked as Rejected.

Do you want to continue?"""
            if slicer.util.confirmYesNoDisplay(message):
                slicer.mrmlScene.Clear()
                try:
                    finish, jobs = self.logic.restartJob()
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 400 and "No images found" in e.response.text:
                        e.args = ("There are no volumes with the status Rejected.",)
                    raise e

                if finish:
                    self.logic.removeLocalData()
                    if self.logic.volume:
                        self.logic.volume.clear()
                        self.logic.volume = None
                    self.logic.getJobs()
                message = "\nNew Job is created: {}\n".format(
                    ", ".join(job["name"] for job in jobs)
                )
                slicer.util.delayDisplay(message, 3000)

    @log_method_call
    def onWorkingDirButton(self) -> None:
        """Run processing when user clicks "Working directory" button."""
        with slicer.util.tryWithErrorDisplay(
            _("Failed to set working directory."), waitCursor=True
        ):
            self.logic.changeWorkingDir()

    @log_method_call
    def onTickSkipSegmentStatus(self) -> None:
        """Run processing when user ticks "Skip segment status check" checkbox."""
        self.logic.skipSegmentStatusCheck = self.ui.skipSegmentStatusCheck.isChecked()


# ------------------------------------ LabelingJobsReviewLogic ----------------------------------- #


class labelingJobsReviewLogic(ScriptedLoadableModuleLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

    def __init__(self, ui) -> None:
        """Called when the logic class is instantiated. Can be used for initializing member variables."""
        ScriptedLoadableModuleLogic.__init__(self)
        self.api = None
        self.teamList = None
        self.volume = None
        self.jobList = None
        self.activeTeam = None
        self.activeJob: LabelingJobInfo = None
        self.savePath = None
        self.ann = None
        self.tagMetas = None
        self.keyIdMap = None
        self.ui = ui
        self.skipSegmentStatusCheck = self.ui.skipSegmentStatusCheck.isChecked()

        envWorkDir = dotenv.get_key(ENV_FILE_PATH, "WORKING_DIR")
        if envWorkDir and os.path.exists(envWorkDir):
            self.workingDir = dotenv.get_key(ENV_FILE_PATH, "WORKING_DIR")
        elif envWorkDir and not os.path.exists(envWorkDir):
            sly.fs.mkdir(envWorkDir)
            self.workingDir = envWorkDir
        else:
            self.workingDir = DEFAULT_WORK_DIR
            dotenv.set_key(ENV_FILE_PATH, "WORKING_DIR", self.workingDir)
        self.ui.workingDirButton.text = str(self.workingDir)
        self.ui.workingDirButton.directory = self.workingDir

    @log_method_call
    def configureUI(self) -> None:
        self.ui.addedTagsLayout.setAlignment(qt.Qt.AlignTop)
        self.ui.availableTagsLayout.setAlignment(qt.Qt.AlignTop)
        is_loaded = dotenv.load_dotenv(ENV_FILE_PATH, override=True)
        is_keep_logged = os.getenv("KEEP_LOGGED")
        if is_loaded and is_keep_logged == "True":
            self.api = sly.Api.from_env()
            if self.api:
                self._getUserName()
                self.ui.loginName.text = f"You are logged in Supervisely as {self.userName}"
                self.ui.serverAddress.hide()
                self.ui.login.hide()
                self.ui.password.hide()
                self.ui.rememberLogin.hide()
                self.ui.connectButton.text = "Disconnect"
                self._activateTeamSelection()
        else:
            self.ui.loginName.hide()
        self.ui.startJobButton.setEnabled(False)
        self.ui.workingDirButton.setFixedHeight(26)

    @log_method_call
    def logIn(self) -> None:
        if self.ui.connectButton.text == "Disconnect":
            self.removeLocalData()
            self.ui.connectButton.text = "Connect"
            self.ui.serverAddress.enabled = True
            self.ui.login.enabled = True
            self.ui.password.enabled = True
            self.ui.serverAddress.text = ""
            self.ui.login.text = ""
            self.ui.password.text = ""
            self.ui.loginName.hide()
            self.ui.rememberLogin.setChecked(False)
            self.ui.serverAddress.show()
            self.ui.login.show()
            self.ui.password.show()
            self.ui.rememberLogin.show()
            self.ui.rememberLogin.enabled = True
            dotenv.set_key(ENV_FILE_PATH, "KEEP_LOGGED", "False")
            self.api = None
            self._deactivateTeamSelection()
            return

        activeModule = dotenv.get_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE")

        self.api = sly.Api.from_credentials(
            server_address=self.ui.serverAddress.text,
            login=self.ui.login.text,
            password=self.ui.password.text,
            override=self.ui.rememberLogin.isChecked(),
            env_file=ENV_FILE_PATH,
        )

        if activeModule:
            dotenv.set_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE", f"{activeModule}")

        self.changeWorkingDir()
        if self.ui.rememberLogin.isChecked():
            self._getUserName()
            dotenv.set_key(ENV_FILE_PATH, "KEEP_LOGGED", "True")
            self.ui.serverAddress.hide()
            self.ui.login.hide()
            self.ui.password.hide()
            self.ui.rememberLogin.hide()
            self.ui.loginName.text = f"You are logged in Supervisely as {self.userName}"
            self.ui.loginName.show()

        if self.api:
            self.ui.serverAddress.enabled = False
            self.ui.login.enabled = False
            self.ui.password.enabled = False
            self.ui.rememberLogin.enabled = False

            self.ui.connectButton.text = "Disconnect"
            self._activateTeamSelection()

    @log_method_call_args
    def getJobs(self, refresh: bool = False) -> None:
        if refresh:
            currentSelection = self.ui.jobSelector.currentText
        self.ui.jobSelector.blockSignals(True)
        self.activeTeam = self._getItemFromSelector(self.teamList, self.ui.teamSelector.currentText)
        try:
            self.jobList = self.api.labeling_job.get_list(
                self.activeTeam.id, reviewer_id=self.api.user.get_my_info().id
            )
        except AttributeError as e:
            e.args = ("This Team doesn't exist or you don't have access to it",)
            raise e
        self._filterVolumeJobs()
        self.ui.jobSelector.clear()
        self.ui.jobSelector.addItem("Select...")
        if not refresh:
            self.ui.jobSelector.currentText = "Select..."
        if len(self.jobList) != 0:
            self.ui.jobSelector.addItems([job.name for job in self.jobList])
            if refresh:
                self.ui.jobSelector.currentText = currentSelection
                if not self.ui.jobSelector.currentText == "Select...":
                    index = self.ui.jobSelector.findText("Select...")
                    self.ui.jobSelector.removeItem(index)
            self.ui.jobSelector.setEnabled(True)
        else:
            self.ui.jobSelector.addItem("No jobs available")
            self.ui.jobSelector.currentText = "No jobs available"
            self.ui.jobSelector.setEnabled(False)
        self.ui.jobSelector.blockSignals(False)

    @log_method_call
    def changeLabelingButtonState(self) -> None:
        if (
            self.ui.jobSelector.currentText == "No jobs available"
            or self.ui.jobSelector.currentText == "Select..."
        ):
            self.ui.startJobButton.setEnabled(False)
        else:
            self.ui.startJobButton.setEnabled(True)

    @log_method_call
    def setActiveJob(self) -> None:
        self.activeJob = self._getItemFromSelector(self.jobList, self.ui.jobSelector.currentText)
        self.ui.activeJob.setChecked(False)
        self.ui.activeJob.setEnabled(False)

    @log_method_call
    def fulfillInfo(self) -> None:
        self.ui.descriptionLabel.clear()
        self.ui.readmeLabel.clear()
        if self.activeJob.description:
            self.ui.descriptionLabel.setText(self.activeJob.description)
        else:
            self.ui.descriptionLabel.setText("No description")
        if self.activeJob.readme:
            self.ui.readmeLabel.setText(self.activeJob.readme)
        else:
            self.ui.readmeLabel.setText("No readme")

    @log_method_call
    def downloadData(self) -> None:

        self._refreshJobInfo()

        self.savePath = os.path.join(self.workingDir, f"{self.activeJob.project_id}")

        if os.path.exists(self.savePath):
            if slicer.util.confirmYesNoDisplay(
                """
This project is already have local data.
To synchronize correctly with the server later you need to download the data again,
this will replace the local data with the current data from the server.

Do you want to continue?"""
            ):
                sly.fs.remove_dir(self.savePath)
            else:
                raise Exception("Data already exists. Select another job or update local data.")

        self.ui.progressBar.setMaximum(len(self.activeJob.entities))
        self.ui.downloadingText.show()
        self.ui.progressBar.show()

        self._dowloadProject()

        self.ui.downloadingText.hide()
        self.ui.progressBar.hide()

        volumes = sly.fs.list_files(f"{self.savePath}/{self.activeJob.dataset_name}/volume")
        volumes = [sly.fs.get_file_name_with_ext(volume) for volume in volumes]
        self.ui.volumeSelector.blockSignals(True)
        self.ui.volumeSelector.clear()
        self.ui.volumeSelector.addItem("Select...")
        self.ui.volumeSelector.currentText = "Select..."
        self.ui.volumeSelector.addItems(volumes)
        self._setVolumeIcon()
        self._setProgressInfo()
        self.ui.volumeSelector.blockSignals(False)
        self.ui.volumeSelector.enabled = True
        self.ui.startJobButton.setEnabled(False)
        self.ui.activeJob.setEnabled(True)
        self.ui.activeJob.setChecked(True)

    @log_method_call
    def loadVolumes(self) -> None:
        if self.volume:
            self.volume.clear()
            self.volume = None

        try:
            self.removeAnnotaionsFromScene()
            self.removeVolumeFromScene()
        except Exception:
            pass

        maskDir = f"{self.savePath}/{self.activeJob.dataset_name}/mask/{self.ui.volumeSelector.currentText}"

        self.volume = volumeClass(
            maskDir=maskDir,
            availableTagsLayout=self.ui.availableTagsLayout,
            addedTagsLayout=self.ui.addedTagsLayout,
        )
        for entity in self.activeJob.entities:
            if entity.get("name") == self.ui.volumeSelector.currentText:
                self.volume.id = entity.get("id")
                break
        self.volume.name = self.ui.volumeSelector.currentText
        self.volume.node = slicer.util.loadVolume(
            f"{self.savePath}/{self.activeJob.dataset_name}/volume/{self.volume.name}",
            {"show": True},
        )

        self._createAnnObject()
        self.createTagButtons()
        self.populateVolumeWithTags()
        self.populateAddedTagsUI()

        self.volume.createSegmentationsOnLoad(logic=self)

        for fig in self.ann.spatial_figures:
            maskKey = fig.key().hex
            maskClassName = fig.parent_object.obj_class.name
            maskObjectId = self.keyIdMap.get_object_id(fig.parent_object.key())
            if maskClassName not in self.activeJob.classes_to_label:
                continue
            maskClassColor = fig.parent_object.obj_class.color
            maskClassColor = (
                maskClassColor[0] / 255,
                maskClassColor[1] / 255,
                maskClassColor[2] / 255,
            )
            segmentation_names = self.volume.getSegmentationNames()

            if maskClassName in segmentation_names:
                segmentation = self.volume.getSegmentationByName(maskClassName)
                segment = segmentClass(
                    f"{maskDir}/{maskKey}.nrrd",
                    maskClassName,
                    maskClassColor,
                    maskKey,
                    segmentationNode=segmentation.segmentationNode,
                    objectId=maskObjectId,
                )
                segmentation.appendSegment(segment)
            else:
                self.volume.createSegmentation(
                    maskDir,
                    maskKey,
                    maskClassName,
                    maskClassColor,
                    maskObjectId,
                )
        self._activateJobButtons()

    @log_method_call
    def loadAnnotations(self) -> None:
        self.removeAnnotaionsFromScene()
        self.volume.addToScene()

    @log_method_call
    def removeVolumeFromScene(self) -> None:
        volumeNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLScalarVolumeNode")
        self._removeNodesFromScene(volumeNodes)

    @log_method_call
    def removeAnnotaionsFromScene(self) -> None:
        labelMapVolumeNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLLabelMapVolumeNode")
        segmentationNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLSegmentationNode")
        displayNodes = slicer.mrmlScene.GetNodesByClass("vtkMRMLSegmentationDisplayNode")
        self._removeNodesFromScene(displayNodes)
        self._removeNodesFromScene(labelMapVolumeNodes)
        self._removeNodesFromScene(segmentationNodes)

    @log_method_call
    def saveAnnotations(self) -> None:
        if self.volume:
            logic = slicer.modules.segmentations.logic()
            for segmentation in self.volume.segmentations:
                segmentation.populateSegments()
                segmentation.markSegmentsForDeletion()
                for segment in segmentation.segments:
                    if not segment.delete:
                        if self.skipSegmentStatusCheck:
                            segment.save(segmentation.maskDir)
                        else:
                            status = logic.GetSegmentStatus(segment.segment)
                            if status == slicer.vtkSlicerSegmentationsModuleLogic.Completed:
                                segment.save(segmentation.maskDir)
                            elif status == slicer.vtkSlicerSegmentationsModuleLogic.InProgress:
                                segment.askForSave(segmentation.maskDir)

    @log_method_call_args
    def changeVolumeStatus(self, status) -> None:
        for entity in self.activeJob.entities:
            if entity["name"] == self.volume.name:
                volumeId = entity["id"]
        self.api.labeling_job.set_entity_review_status(self.activeJob.id, volumeId, status)

    @log_method_call_args
    def changeJobStatus(
        self, status: Literal["pending", "in_progress", "on_review", "completed", "stopped"]
    ) -> None:
        """Change job status to 'status'

        Args:
            status (str): New status. Can be "pending", "in_progress", "on_review", "completed", "stopped"
        """
        currentStatus = self.api.labeling_job.get_status(self.activeJob.id).value
        setStatus = self.api.labeling_job.set_status
        if currentStatus == "pending" and status in ["in_progress", "stopped"]:
            setStatus(self.activeJob.id, status)
        elif currentStatus == "in_progress" and status in ["on_review", "stopped"]:
            setStatus(self.activeJob.id, status)
        elif currentStatus == "on_review" and status in ["completed", "stopped"]:
            setStatus(self.activeJob.id, status)

    @log_method_call
    def uploadAnnObjectChangesToServer(self) -> None:
        from uuid import UUID

        for segmentation in self.volume.segmentations:
            for segment in segmentation.segments:
                if segment.delete:
                    # Remove objects from server
                    self.api.volume.object.remove_batch([segment.objectId])
                    # Remove objects from annotation object
                    self.ann = self.ann.remove_objects(
                        [self.keyIdMap.get_object_key(segment.objectId)]
                    )
                    # Remove objects and its figures from keyIdMap object
                    self.keyIdMap.remove_object(id=segment.objectId)
                    self.keyIdMap.remove_figure(key=UUID(segment.maskKey))
                    # Update annotation and keyIdMap files
                    self.ann.dump_json(
                        f"{self.savePath}/{self.activeJob.dataset_name}/ann/{self.volume.name}.json",
                        key_id_map=self.keyIdMap,
                    )
                    self.keyIdMap.dump_json(f"{self.savePath}/key_id_map.json")
                    # Remove segments in Slicer
                    segmentation.removeSegmentBySegment(segment)
                else:
                    if segment.maskKey:
                        # Create 3D Mmask figure and upload to project on server
                        mask_uuid = UUID(segment.maskKey)
                        _, mask_bytes = sly.Mask3D._bytes_from_nrrd(segment.path)
                        self.api.volume.figure.upload_sf_geometries(
                            [mask_uuid], {mask_uuid: mask_bytes}, self.keyIdMap
                        )
                    else:
                        try:
                            # Create new figure from file that doesn't exist on server
                            new_figure = sly.Mask3D.create_from_file(segment.path)
                        except ValueError as e:
                            if "Instead got [0]" in e.args[0]:
                                e.args = (f"Segment {segment.name} is empty",)
                            raise e
                        figure_class = self.projectMeta.obj_classes.get(segmentation.name)
                        # Create new object of corresponding class
                        new_object = sly.VolumeObject(figure_class, mask_3d=new_figure)
                        volumeInfo = self.api.volume.get_info_by_name(
                            parent_id=self.activeJob.dataset_id, name=self.volume.name
                        )
                        # Create new annotation object that contains only new object
                        new_ann = sly.VolumeAnnotation(
                            volumeInfo.meta,
                            objects=[new_object],
                            spatial_figures=[new_object.figure],
                        )
                        # Create copy of keyIdMap object to compare it with new one after upload
                        oldKeyIdMapDict = copy.deepcopy(self.keyIdMap).to_dict()
                        # Upload new annotation object to server
                        self.api.volume.annotation.append(volumeInfo.id, new_ann, self.keyIdMap)
                        # keyIdMap object updated during upload, so we can compare it with old one
                        newKeyIdMapDict = self.keyIdMap.to_dict()
                        # Get maskKey and objectId of new segment
                        segment.maskKey = list(
                            set(newKeyIdMapDict["figures"]) - set(oldKeyIdMapDict["figures"])
                        ).pop()
                        objectKey = list(
                            set(newKeyIdMapDict["objects"]) - set(oldKeyIdMapDict["objects"])
                        ).pop()
                        segment.objectId = self.keyIdMap.get_object_id(UUID(objectKey))
                        # Update segment path in segment object
                        newPath = os.path.dirname(segment.path) + f"/{segment.maskKey}.nrrd"
                        os.rename(segment.path, newPath)
                        segment.path = newPath
                        # Update annotation and keyIdMap files
                        self.ann = self.ann.add_objects([new_object])
                        self.ann.dump_json(
                            f"{self.savePath}/{self.activeJob.dataset_name}/ann/{self.volume.name}.json",
                            key_id_map=self.keyIdMap,
                        )
                        self.keyIdMap.dump_json(f"{self.savePath}/key_id_map.json")

    # -------------------------------------- Tag Methods Section ------------------------------------- #

    @staticmethod
    def onTagButtonAdd(button, logic, checked, value=None):
        """
        Run processing when user clicks "Add" button.
        Value used only for population of already added tags.
        """
        newButton = qt.QPushButton()
        newText = button.text
        if value is None:
            if ": STR" in newText:
                dialog = InputDialog(icon=button.icon, title=newText, label="Enter text")
                if not dialog.execute_and_assign_tag(newText, ": STR    ➡️", newButton, logic):
                    return
            elif ": NUM" in newText:
                dialog = InputDialog(
                    validate="number", icon=button.icon, title=newText, label="Enter number"
                )
                if not dialog.execute_and_assign_tag(newText, ": NUM    ➡️", newButton, logic):
                    return
            elif ": ONEOF" in newText:
                tagName = newText.split(": ONEOF")[0]
                for tag in logic.tagMetas:
                    if tag.name == tagName:
                        tagOptions = tag.possible_values
                        continue
                dialog = InputDialog(
                    options=tagOptions,
                    icon=button.icon,
                    title=newText,
                    label="Choose one of the options",
                )
                if not dialog.execute_and_assign_tag(newText, ": ONEOF    ➡️", newButton, logic):
                    return
            else:
                newButton.setText(newText.replace("    ➡️", "    🗑️"))
                tag = {"name": newText.replace("    ➡️", ""), "value": None}
                if not logic.volume.hasTag(tag["name"]):
                    logic.volume.assignTag(tag)
                else:
                    InputDialog.show_notification_none(
                        button.icon, f"Tag [{tag['name']}] already exists.", 2000
                    )
                    return
        else:
            for clearItem in ["    ➡️", "    🗑️", ": ONEOF", ": NUM", ": STR"]:
                newText = newText.replace(clearItem, "")
            if value == "None":
                value = None
                newButton.setText(f"{newText}    🗑️")
            else:
                newButton.setText(f"{newText}: {value}    🗑️")
            tag = {"name": newText, "value": value}
            if not logic.volume.hasTag(tag["name"]):
                logic.volume.assignTag(tag)
        newButton.setIcon(button.icon)
        newButton.setFixedHeight(button.height)
        newButton.setStyleSheet("text-align: left;")
        logic.ui.addedTagsLayout.addWidget(newButton)
        logic.ui.noneTags_right.hide()
        newButton.clicked.connect(partial(logic.onTagButtonRemove, newButton, logic))

    @staticmethod
    def onTagButtonRemove(button, logic, checked):
        logic.ui.addedTagsLayout.removeWidget(button)
        if ": " in button.text:
            name, value = button.text.split(": ")
            value = value.replace("    🗑️", "")
        else:
            name = button.text
            value = None
            name = name.replace("    🗑️", "")
        for tagButton in logic.volume.tagButtons:
            if name in tagButton.text and ": NUM" in tagButton.text:
                value = int(value)
                continue
        logic.volume.removeTag(name, value)
        button.deleteLater()

    @log_method_call
    def createTagButtons(self):
        self.tagMetas = self.projectMeta.tag_metas.items()
        for tagMeta in self.tagMetas:
            if (
                tagMeta.name in self.activeJob.tags_to_label
                and tagMeta.applicable_to == sly.TagApplicableTo.IMAGES_ONLY
            ):
                if tagMeta.value_type == sly.TagValueType.NONE:
                    button = qt.QPushButton(tagMeta.name + "    ➡️")
                elif tagMeta.value_type == sly.TagValueType.ANY_STRING:
                    button = qt.QPushButton(tagMeta.name + ": STR" + "    ➡️")
                elif tagMeta.value_type == sly.TagValueType.ANY_NUMBER:
                    button = qt.QPushButton(tagMeta.name + ": NUM" + "    ➡️")
                elif tagMeta.value_type == sly.TagValueType.ONEOF_STRING:
                    button = qt.QPushButton(tagMeta.name + ": ONEOF" + "    ➡️")
                button.setStyleSheet("text-align: left;")
                height = button.sizeHint.height()
                self.ui.availableTagsLayout.addWidget(button)
                button.clicked.connect(partial(self.onTagButtonAdd, button, self))
                button.setIcon(self._createColorIcon(tagMeta.color))
                button.setFixedHeight(height)
                self.volume.tagButtons.append(button)
        if len(self.tagMetas) != 0:
            self.ui.noneTags_left.hide()

    @log_method_call
    def populateVolumeWithTags(self) -> None:
        for tagInfo in self.ann.tags:
            tag = {"name": tagInfo.name, "value": tagInfo.value}
            self.volume.tags.append(tag)

    @log_method_call
    def populateAddedTagsUI(self) -> None:
        for tag in self.volume.tags:
            for button in self.volume.tagButtons:
                if tag["name"] == button.text.replace("    ➡️", "").split(": ")[0]:
                    if tag["value"]:
                        self.onTagButtonAdd(button, self, False, tag["value"])
                    else:
                        self.onTagButtonAdd(button, self, False, "None")
                    continue

    @log_method_call
    def uploadTagsChangesToServer(self) -> None:
        if self.volume.tagsChanged:
            # Get all tags from volume and annotation object
            newTags = []
            forDeleteTags = []
            volumeTagsSet = set((tag["name"], tag["value"]) for tag in self.volume.tags)
            annTagsSet = set((tag.meta.name, tag.value) for tag in self.ann.tags)
            # Get tags that should be added and removed
            tagsToAdd = volumeTagsSet - annTagsSet
            tagsToRemove = annTagsSet - volumeTagsSet
            # Convert sets to lists of dictionaries
            tagsToAdd = [{"name": name, "value": value} for name, value in tagsToAdd]
            tagsToRemove = [{"name": name, "value": value} for name, value in tagsToRemove]

            for tag in tagsToRemove:
                # Get tag key for current tag (this tag also exists on server)
                tagKey = [
                    annTag.key()
                    for annTag in self.ann.tags
                    if annTag.name == tag["name"] and annTag.value == tag["value"]
                ][0]
                tagId = self.keyIdMap.get_tag_id(tagKey)
                self.api.volume.tag.remove_from_volume(tagId)
                self.keyIdMap.remove_tag(tagKey)
                # Add tag key to list of tags that should be removed from annotation object
                forDeleteTags.append(tagKey)

            for tag in tagsToAdd:
                # Get tagMeta object for current tag
                tagMeta = self.projectMeta.tag_metas.get(tag["name"])
                # Upload new tag to server and get its id
                value = tag["value"]
                newTagId = self.api.volume.tag.append_to_volume(
                    volume_id=self.volume.id,
                    tag_id=tagMeta.sly_id,
                    value=value,
                    tag_meta=tagMeta,
                )
                # Create new tag object that will be added to annotation object to update it to state as on server
                # without downloading and replace full annotation object
                newTag = sly.VolumeTag(tagMeta, value=value, sly_id=newTagId)
                self.keyIdMap.add_tag(newTag.key(), newTag.sly_id)
                # Add new tag object to list of tags that should be added to annotation object
                newTags.append(newTag)

            # Update annotation object with changes
            self.ann = self.ann.remove_tags(forDeleteTags)
            self.ann = self.ann.add_tags(newTags)

            # Update annotation and keyIdMap files
            self.ann.dump_json(
                self.savePath + f"/{self.activeJob.dataset_name}/ann/{self.volume.name}.json"
            )
            self.keyIdMap.dump_json(self.savePath + "/key_id_map.json")
            # Reset tagsChanged flag
            self.volume.tagsChanged = False
        else:
            logging.info("Tags are not changed, nothing to upload")
            return

    # ----------------------------------------- Other Methods ---------------------------------------- #

    @log_method_call
    def removeLocalData(self) -> None:
        if self.savePath and os.path.exists(self.savePath):
            sly.fs.remove_dir(self.savePath)
            self.savePath = None

    @log_method_call
    def changeWorkingDir(self) -> None:
        self.workingDir = self.ui.workingDirButton.directory
        self.ui.workingDirButton.text = self.ui.workingDirButton.directory
        dotenv.set_key(ENV_FILE_PATH, "WORKING_DIR", self.workingDir)

    # ------------------------------------------ UI Methods ------------------------------------------ #

    @log_method_call
    def removeVolumeFromJobList(self) -> None:
        self.ui.volumeSelector.blockSignals(True)
        self.ui.volumeSelector.removeItem(self.ui.volumeSelector.currentIndex)
        self.ui.volumeSelector.setCurrentIndex(0)
        self.ui.volumeSelector.blockSignals(False)
        count = self.ui.volumeSelector.count
        if count == 0:
            self.ui.volumeSelector.setEnabled(False)
            self.ui.startJobButton.setEnabled(False)
            self.ui.volumeSelector.currentText = "No volumes available"
            self.ui.acceptButton.setEnabled(False)
            self.ui.rejectButton.setEnabled(False)
            self._deactivateJobButtons()
        else:
            self.ui.volumeSelector.blockSignals(True)
            self.ui.volumeSelector.setCurrentIndex(-1)
            if count != 1:
                self.ui.volumeSelector.currentText = "Select..."
                self.ui.volumeSelector.blockSignals(False)
            else:
                self.ui.volumeSelector.blockSignals(False)
                self.ui.volumeSelector.setCurrentIndex(0)

    @log_method_call
    def setVolumeStatusUI(self) -> None:
        self._refreshJobInfo()
        self._setVolumeIcon()
        self._setProgressInfo()

    def restartJob(self) -> None:
        finishCurrent = False
        restartRejected = False
        if slicer.util.confirmYesNoDisplay("\nDo you want to Finish current job?\n"):
            finishCurrent = True
        if self.ui.restartRejected.isChecked():
            restartRejected = True
        jobs = self.api.labeling_job.restart(
            self.activeJob.id,
            complete_existing=finishCurrent,
            only_rejected_entities=restartRejected,
        )
        return finishCurrent, jobs

    @log_method_call
    def _activateTeamSelection(self) -> None:
        self.ui.downloadingText.hide()
        self.ui.progressBar.hide()
        self.ui.teamJobs.setChecked(True)
        self.ui.teamJobs.setEnabled(True)
        self.ui.teamSelector.addItem("Select...")
        self.ui.jobSelector.addItem("Select...")
        self.teamList = self.api.team.get_list()
        self.ui.teamSelector.addItems([team.name for team in self.teamList])
        self.ui.teamSelector.currentText = "Select..."
        self.ui.jobSelector.currentText = "Select..."
        self.ui.teamSelector.setEnabled(True)
        self.ui.jobSelector.setEnabled(False)

    @log_method_call
    def _deactivateTeamSelection(self) -> None:
        self.ui.teamSelector.blockSignals(True)
        self.ui.jobSelector.blockSignals(True)
        self.ui.teamSelector.clear()
        self.ui.teamSelector.addItem("Select...")
        self.ui.teamSelector.currentText = "Select..."
        self.ui.teamSelector.setEnabled(False)
        self.ui.jobSelector.clear()
        self.ui.jobSelector.addItem("Select...")
        self.ui.jobSelector.currentText = "Select..."
        self.ui.jobSelector.setEnabled(False)
        self.ui.teamJobs.setEnabled(False)
        self.ui.teamJobs.setChecked(False)
        self.ui.activeJob.setChecked(False)
        self.ui.activeJob.setEnabled(False)
        self.ui.teamSelector.blockSignals(False)
        self.ui.jobSelector.blockSignals(False)

    @log_method_call
    def _activateJobButtons(self) -> None:
        self.ui.acceptButton.setEnabled(True)
        self.ui.rejectButton.setEnabled(True)
        self.ui.finishButton.setEnabled(True)
        self.ui.saveButton.setEnabled(True)
        self.ui.tags.setEnabled(True)

    @log_method_call
    def _deactivateJobButtons(self, deactivateSubmit=False) -> None:
        self.ui.acceptButton.setEnabled(False)
        self.ui.rejectButton.setEnabled(False)
        self.ui.saveButton.setEnabled(False)
        self.ui.tags.setEnabled(False)
        if deactivateSubmit:
            self.ui.finishButton.setEnabled(False)

    # --------------------------------------- Technical Methods -------------------------------------- #

    @log_method_call_args
    def _dowloadProject(self, downloadVolumes=True) -> None:
        """
        Download project from server and create keyIdMap and projectMeta.
        If tempPath is not None, download to tempPath and don't create keyIdMap and projectMeta.
        """
        self.api.add_header("x-job-id", str(self.activeJob.id))
        sly.VolumeProject.download(
            self.api,
            self.activeJob.project_id,
            self.savePath,
            [self.activeJob.dataset_id],
            download_volumes=downloadVolumes,
            progress_cb=self.ui.progressBar.setValue,
        )
        self.api.pop_header("x-job-id")
        self.ui.progressBar.reset()
        self.keyIdMap = sly.KeyIdMap.load_json(f"{self.savePath}/key_id_map.json")
        with open(f"{self.savePath}/meta.json", "r") as f:
            metaJson = load(f)
        self.projectMeta = sly.ProjectMeta.from_json(metaJson)

    @log_method_call
    def _createAnnObject(self) -> None:
        with open(
            f"{self.savePath}/{self.activeJob.dataset_name}/ann/{self.volume.name}.json",
            "r",
        ) as f:
            annJson = load(f)
        self.ann = sly.VolumeAnnotation.from_json(annJson, self.projectMeta)

    @log_method_call
    def _getUserName(self):
        user_info = self.api.user.get_my_info()
        if user_info.name:
            self.userName = user_info.name
        else:
            self.userName = user_info.login

    @log_method_call_args
    def _getItemFromSelector(self, itemsList, selectorText) -> None:
        """Get item by name from selector"""
        for item in itemsList:
            if item.name == selectorText:
                return item

    @log_method_call
    def _filterVolumeJobs(self) -> None:
        """Filter jobs that are related to volumes projects"""
        projectIds = [job.project_id for job in self.jobList]
        filteredProjectIds = []
        for projectId in list(set(projectIds)):
            if self.api.project.get_info_by_id(projectId).type == "volumes":
                filteredProjectIds.append(projectId)

        self.jobList = [job for job in self.jobList if job.project_id in filteredProjectIds]
        self.jobList = [job for job in self.jobList if job.status in ["on_review"]]

    @log_method_call_args
    def _removeNodesFromScene(self, collection) -> None:
        if collection.GetNumberOfItems() == 0:
            return
        collection.InitTraversal()
        node = collection.GetNextItemAsObject()
        while node is not None:
            slicer.mrmlScene.RemoveNode(node)
            node = collection.GetNextItemAsObject()

    @log_method_call
    def _setVolumeIcon(self) -> None:
        """Set icon to volumeSelector items according to their reviewStatus."""
        moduleDir = os.path.dirname(slicer.util.modulePath(self.__module__))
        acceptedPath = os.path.join(moduleDir, "Resources/Icons", "accepted.svg")
        rejectedPath = os.path.join(moduleDir, "Resources/Icons", "rejected.svg")
        donePath = os.path.join(moduleDir, "Resources/Icons", "done.svg")
        nonePath = os.path.join(moduleDir, "Resources/Icons", "none.svg")
        self.ui.volumeSelector.blockSignals(True)
        for entity in self.activeJob.entities:
            if entity["reviewStatus"] == "accepted":
                icon = qt.QIcon(acceptedPath)
            elif entity["reviewStatus"] == "rejected":
                icon = qt.QIcon(rejectedPath)
            elif entity["reviewStatus"] == "done":
                icon = qt.QIcon(donePath)
            elif entity["reviewStatus"] == "none":
                icon = qt.QIcon(nonePath)
            idx = self.ui.volumeSelector.findText(entity["name"])
            if idx < 0:
                logging.warning(
                    f'Volume {entity["name"]} is not found in the list when setting "{icon}" icon'
                )
                continue
            self.ui.volumeSelector.setItemIcon(idx, icon)
        self.ui.volumeSelector.blockSignals(False)

    @log_method_call
    def _setProgressInfo(self) -> None:
        accepted = 0
        rejected = 0
        total = len(self.activeJob.entities)
        for entity in self.activeJob.entities:
            if entity["reviewStatus"] == "accepted":
                accepted += 1
            if entity["reviewStatus"] == "rejected":
                rejected += 1
        if total != 0:
            self.ui.inProgressCounterAll.text = f"of {total}"
            self.ui.inProgressCounter.text = f"👍{accepted} 👎{rejected}"

    @log_method_call
    def _refreshJobInfo(self) -> None:
        self.activeJob = self.api.labeling_job.get_info_by_id(self.activeJob.id)

    @log_method_call_args
    def _createColorIcon(self, color):
        # moduleDir = os.path.dirname(slicer.util.modulePath(self.__module__))
        # labelIconPath = os.path.join(moduleDir, "Resources/Icons", "done.svg")
        # pixmap = qt.QPixmap(100, 100)
        # pixmap.fill(qt.Qt.transparent)
        # painter = qt.QPainter(pixmap)
        # renderer = QSvgRenderer(labelIconPath)
        # painter.setBrush(qt.QColor(color[0], color[1], color[2]))
        # painter.setPen(qt.QColor(color[0], color[1], color[2]))
        # renderer.render(painter)
        # painter.end()
        pixmap = qt.QPixmap(10, 10)
        pixmap.fill(qt.QColor(color[0], color[1], color[2]))
        icon = qt.QIcon(pixmap)
        return icon
