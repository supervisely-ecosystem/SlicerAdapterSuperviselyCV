import os
from pathlib import Path

import requests
import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleWidget,
)

try:
    import dotenv  # isort:skip
except ModuleNotFoundError:
    pass


from moduleLib import (
    SuperviselyDialog,
    block_widget,
    import_supervisely,
    log_method_call,
    log_method_call_args,
    restore_libraries,
)
from moduleLib.baseLogic import DEFAULT_WORK_DIR, ENV_FILE_PATH, BaseLogic

# -------------------------------------- labelingJobsReviewing ----------------------------------- #


class labelingJobsReviewing(ScriptedLoadableModule):
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


# ----------------------------------- labelingJobsReviewingWidget ----------------------------------- #


class labelingJobsReviewingWidget(ScriptedLoadableModuleWidget):
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
        uiWidget = slicer.util.loadUI(self.resourcePath("UI/labelingJobsReviewing.ui"))
        self.layout.addWidget(uiWidget)
        self.ui = slicer.util.childWidgetVariables(uiWidget)

        # Set scene in MRML widgets. Make sure that in Qt designer the top-level qMRMLWidget's
        # "mrmlSceneChanged(vtkMRMLScene*)" signal in is connected to each MRML widget's.
        # "setMRMLScene(vtkMRMLScene*)" slot.
        uiWidget.setMRMLScene(slicer.mrmlScene)

        # Create logic class. Logic implements all computations that should be possible to run
        # in batch mode, without a graphical user interface.
        self.logic = labelingJobsReviewingLogic(self.ui)

        # Configure default UI state
        self.logic.configureUI()

        # Buttons
        self.ui.connectButton.connect("clicked(bool)", self.onConnectButton)
        self.ui.refreshJobsButton.connect("clicked(bool)", self.onRefreshJobsButton)
        self.ui.startJobButton.connect("clicked(bool)", self.onStartJobButton)
        self.ui.saveButton.connect("clicked(bool)", self.onSaveButton)
        self.ui.acceptButton.connect("clicked(bool)", self.onAcceptButton)
        self.ui.rejectButton.connect("clicked(bool)", self.onRejectButton)
        self.ui.restartButton.connect("clicked(bool)", self.onRestartButton)
        self.ui.finishButton.connect("clicked(bool)", self.onFinishButton)
        self.ui.workingDirButton.directoryChanged.connect(self.onWorkingDirButton)
        self.ui.syncCurrentJobButton.connect("clicked(bool)", self.onSyncCurrentJobButton)
        self.ui.restoreLibrariesButton.connect("clicked(bool)", self.onRestoreLibrariesButton)

        # Lists
        self.ui.teamSelector.currentIndexChanged.connect(self.onSelectTeam)
        self.ui.jobSelector.currentIndexChanged.connect(self.onSelectJob)
        # self.ui.jobSelector.currentTextChanged.connect(self.onSelectJob)
        self.ui.volumeSelector.currentIndexChanged.connect(self.onSelectVolume)

        # Checkboxes
        self.ui.skipSegmentStatusCheck.connect("clicked(bool)", self.onTickSkipSegmentStatus)

    def enter(self) -> None:
        """Called each time the user opens this module."""
        import logging

        if self.ready_to_start:
            slicer.util.setDataProbeVisible(False)
            logger = logging.getLogger()
            original_level = logger.getEffectiveLevel()
            logger.setLevel(logging.CRITICAL)
            activeModule = dotenv.get_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE")
            logger.setLevel(original_level)
            if not activeModule:
                dotenv.set_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE", f"{self.moduleName}")
            elif activeModule != self.moduleName:
                slicer.util.reloadScriptedModule(activeModule)
                dotenv.set_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE", f"{self.moduleName}")

    def cleanup(self):
        """Called when the application is about to close."""
        slicer.mrmlScene.Clear()
        dotenv.unset_key(ENV_FILE_PATH, "ACTIVE_SLY_MODULE")

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
                if self.logic.volume and SuperviselyDialog(
                    "Do you want to save changes before select another team?", type="confirm"
                ):
                    self.logic.saveAnnotations()
                    self.logic.uploadAnnObjectChangesToServer()
                    self.logic.uploadTagsChangesToServer()
            slicer.mrmlScene.Clear()
            self.logic.removeLocalData()
            if self.logic.volume:
                self.logic.volume.clear()
                self.logic.volume = None
            self.logic.getJobs()
            self.ui.workingDirButton.setEnabled(True)
            self.ui.activeJob.setChecked(False)
            self.ui.activeJob.setEnabled(False)
            self.ui.refreshJobsButton.setEnabled(True)
            self.ui.syncCurrentJobButton.setEnabled(False)

    @log_method_call_args
    def onSelectJob(self, sync: bool = False) -> None:
        """Run processing when user change "Job" in selector."""
        with slicer.util.tryWithErrorDisplay(_("Failed to select Job."), waitCursor=True):
            index = self.ui.jobSelector.findText("Select...")
            self.ui.jobSelector.removeItem(index)
            if self.logic.savePath and os.path.exists(self.logic.savePath):
                text = "Do you want to save changes before select another job?"
                if sync:
                    text = "Do you want to save changes before sync current job?"
                if self.logic.volume and SuperviselyDialog(text, type="confirm"):
                    self.logic.saveAnnotations()
                    self.logic.uploadAnnObjectChangesToServer()
                    self.logic.uploadTagsChangesToServer()
            slicer.mrmlScene.Clear()
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
    def onSyncCurrentJobButton(self) -> None:
        """Run processing when user clicks "Sync Current Job" button."""
        with slicer.util.tryWithErrorDisplay(
            _("Failed to synchronize current job."), waitCursor=True
        ):
            self.onSelectJob(sync=True)
            self.onStartJobButton()

    @log_method_call
    def onStartJobButton(self) -> None:
        """Run processing when user clicks "Start labeling" button."""
        with slicer.util.tryWithErrorDisplay(
            _("Failed to download project data."), waitCursor=True
        ):
            if self.logic.volume:
                self.logic.volume.clear()
                self.logic.volume = None
            if not self.logic.downloadData():
                return
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
                slicer.mrmlScene.Clear()
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
            if SuperviselyDialog(message, type="confirm"):
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
                SuperviselyDialog(message, type="delay", delay=3000)

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

    @log_method_call
    def onRestoreLibrariesButton(self) -> None:
        """Run processing when user clicks "Restore libraries" button."""
        restore_libraries(self)


# ------------------------------------ labelingJobsReviewingLogic ----------------------------------- #


class labelingJobsReviewingLogic(BaseLogic):
    """This class should implement all the actual
    computation done by your module.  The interface
    should be such that other python code can import
    this class and make use of the functionality without
    requiring an instance of the Widget.
    Uses ScriptedLoadableModuleLogic base class, available at:
    https://github.com/Slicer/Slicer/blob/main/Base/Python/slicer/ScriptedLoadableModule.py
    """

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
                self.ui.jobSelector.currentText = (
                    currentSelection
                    if currentSelection in [job.name for job in self.jobList]
                    else "Select..."
                )
                if not self.ui.jobSelector.currentText == "Select...":
                    index = self.ui.jobSelector.findText("Select...")
                    self.ui.jobSelector.removeItem(index)
            self.ui.jobSelector.setEnabled(True)
        else:
            self.ui.jobSelector.addItem("No jobs available")
            self.ui.jobSelector.currentText = "No jobs available"
            self.ui.jobSelector.setEnabled(False)
        self.ui.jobSelector.blockSignals(False)

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
            self.ui.syncCurrentJobButton.setEnabled(False)
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

    def restartJob(self) -> None:
        finishCurrent = False
        restartRejected = False
        if SuperviselyDialog("\nDo you want to Finish current job?\n", type="confirm"):
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
    def _activateJobButtons(self) -> None:
        self.ui.acceptButton.setEnabled(True)
        self.ui.rejectButton.setEnabled(True)
        self.ui.finishButton.setEnabled(True)
        self.ui.saveButton.setEnabled(True)
        if self._createdButtons > 0:
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
