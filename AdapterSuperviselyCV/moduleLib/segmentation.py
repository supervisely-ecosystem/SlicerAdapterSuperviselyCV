from typing import List

import qt
import slicer


class segmentClass:

    def __init__(
        self,
        path: str = None,
        name: str = None,
        color: list = None,
        maskKey: str = None,
        segment=None,
        segmentationNode=None,
        objectId=None,
        delete=False,
    ):
        self.path = path
        self.name = name
        self.color = color
        self.maskKey = maskKey
        self.segment = segment
        self.segmentationNode = segmentationNode
        self.objectId = objectId
        self.delete = delete

        if self.path and not self.segment:
            volumeNode = slicer.util.loadLabelVolume(self.path)
            if not self.segmentationNode:
                self.segmentationNode = slicer.vtkMRMLSegmentationNode()
            else:
                numOfSegments = self.segmentationNode.GetSegmentation().GetNumberOfSegments()
            slicer.modules.segmentations.logic().ImportLabelmapToSegmentationNode(
                volumeNode, self.segmentationNode
            )
            self.segment = self.segmentationNode.GetSegmentation().GetNthSegment(numOfSegments)
            if slicer.mrmlScene.GetNodeByID(volumeNode.GetID()) is not None:
                slicer.mrmlScene.RemoveNode(volumeNode)
            volumeNode = None
        elif self.segment and not self.path:
            self.name = self.segment.GetName()
            self.color = self.segment.GetColor()

        if self.name and self.segment:
            self.setName(self.name)

        if self.color and self.segment:
            self.setColor(self.color)

    def setColor(self, color):
        self.segment.SetColor(color)

    def setName(self, name):
        self.segment.SetName(name)

    def setMaskKey(self, maskKey):
        self.maskKey = maskKey

    def getSegmentId(self):
        return self.name

    def getSegmentationNode(self):
        return self.segmentationNode

    def getSegment(self):
        return self.segment

    def clear(self):
        self.segment = None
        self.path = None
        self.name = None
        self.color = None
        self.maskKey = None
        self.segmentationNode = None
        self.objectId = None
        self.delete = None

    def save(self, maskDir=None):
        logic = slicer.modules.segmentations.logic()
        labelmapVolumeNode = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLabelMapVolumeNode")
        segmentId = self.segmentationNode.GetSegmentation().GetSegmentIdBySegment(self.segment)
        logic.ExportSegmentsToLabelmapNode(
            self.segmentationNode,
            [segmentId],
            labelmapVolumeNode,
            None,
            slicer.vtkSegmentation.EXTENT_REFERENCE_GEOMETRY,
        )
        if self.path is None:
            if maskDir is None:
                raise ValueError("Save path is not defined. Please provide maskDir argument.")
            self.path = f"{maskDir}/{self.name}_{segmentId}.nrrd"
        slicer.util.saveNode(labelmapVolumeNode, self.path)
        slicer.mrmlScene.RemoveNode(labelmapVolumeNode)
        labelmapVolumeNode = None

    def askForSave(self, maskDir=None):
        logic = slicer.modules.segmentations.logic()
        answer = slicer.util.confirmOkCancelDisplay(
            f"Do you want to save changes in {self.name} segment which is in progress?"
        )
        if answer:
            logic.SetSegmentStatus(self.segment, slicer.vtkSlicerSegmentationsModuleLogic.Completed)
            self.save(maskDir)


class segmentationClass:

    def __init__(
        self,
        name: str,
        volumeNode=None,
        segments: List[segmentClass] = None,
        maskDir=None,
    ):
        self.name = name
        self.VolumeNode = volumeNode
        if segments is None:
            self.segments = []
        else:
            self.segments = segments
        self.maskDir = maskDir

        if self.VolumeNode:
            self.segmentationNode = slicer.vtkMRMLSegmentationNode()
            self.segmentationNode.SetReferenceImageGeometryParameterFromVolumeNode(self.VolumeNode)
            slicer.mrmlScene.AddNode(self.segmentationNode)
            shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
            shNode.SetItemParent(
                shNode.GetItemByDataNode(self.segmentationNode), shNode.GetSceneItemID()
            )
            self.setName(name)
            if len(self.segments) != 0:
                for segment in self.segments:
                    self.appendSegment(segment)
            displayNode = self.segmentationNode.GetDisplayNode()
            if displayNode is None:
                displayNode = slicer.vtkMRMLSegmentationDisplayNode()
                slicer.mrmlScene.AddNode(displayNode)
                self.segmentationNode.SetAndObserveDisplayNodeID(displayNode.GetID())
            displayNode.SetVisibility(True)

    def setName(self, name):
        self.segmentationNode.SetName(name)

    def addToScene(self):
        segmentation = self.segmentationNode.GetSegmentation()
        if slicer.mrmlScene.GetNodeByID(self.segmentationNode.GetID()) is None:
            slicer.mrmlScene.AddNode(self.segmentationNode)
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shNode.SetItemParent(
            shNode.GetItemByDataNode(self.segmentationNode), shNode.GetSceneItemID()
        )
        for segment in self.segments:
            segmentation.AddSegment(segment.segment)
        displayNode = self.segmentationNode.GetDisplayNode()
        if displayNode is None:
            displayNode = slicer.vtkMRMLSegmentationDisplayNode()
            slicer.mrmlScene.AddNode(displayNode)
            self.segmentationNode.SetAndObserveDisplayNodeID(displayNode.GetID())
        displayNode.SetVisibility(True)

    def removeFromScene(self):
        if self.segmentationNode is not None:
            slicer.mrmlScene.RemoveNode(self.segmentationNode)

    def appendSegment(self, segment: segmentClass):
        """Add segment to segments list"""
        self.segments.append(segment)

    def addSegment(self, segment: segmentClass):
        """Add segment to segmentation object"""
        self.segmentationNode.GetSegmentation().AddSegment(segment.segment)

    def getSegmentNames(self):
        return [segment.name for segment in self.segments]

    def getSegmentByName(self, segmentName):
        for segment in self.segments:
            if segment.name == segmentName:
                return segment

    def getSegmentById(self, segmentId):
        for segment in self.segments:
            if segment.getSegmentId() == segmentId:
                return segment

    def removeSegmentById(self, segmentId):
        """Remove segment from segmentation object and segments list"""
        self.segments = [
            segment for segment in self.segments if segment.getSegmentId() != segmentId
        ]
        self.segmentationNode.GetSegmentation().RemoveSegment(segmentId)

    def removeSegmentBySegment(self, segment: segmentClass):
        """Remove segment object from segmentation object and delete itself"""
        self.segments.remove(segment)
        segment.clear()
        segment = None

    def clear(self):
        """Clear segmentation object and remove it from scene, break all Node connections"""
        for segment in self.segments:
            segment.clear()
        self.segments = []
        if slicer.mrmlScene.GetNodeByID(self.segmentationNode.GetID()) is not None:
            slicer.mrmlScene.RemoveNode(self.segmentationNode)
        self.segmentationNode = None
        self.VolumeNode = None

    @classmethod
    def createSegmentationFromFile(cls, maskDir, name, color, maskKey, objectId):
        maskPath = f"{maskDir}/{maskKey}.nrrd"
        instance = cls(name)
        instance.segmentationNode = slicer.util.loadSegmentation(maskPath, {"name": name})
        if slicer.mrmlScene.GetNodeByID(instance.segmentationNode.GetID()) is None:
            slicer.mrmlScene.AddNode(instance.segmentationNode)
        shNode = slicer.vtkMRMLSubjectHierarchyNode.GetSubjectHierarchyNode(slicer.mrmlScene)
        shNode.SetItemParent(
            shNode.GetItemByDataNode(instance.segmentationNode), shNode.GetSceneItemID()
        )
        displayNode = instance.segmentationNode.GetDisplayNode()
        if displayNode is None:
            displayNode = slicer.vtkMRMLSegmentationDisplayNode()
            slicer.mrmlScene.AddNode(displayNode)
            instance.segmentationNode.SetAndObserveDisplayNodeID(displayNode.GetID())
        displayNode.SetVisibility(True)
        baseSegment = instance.segmentationNode.GetSegmentation().GetNthSegment(0)
        if baseSegment:
            baseSegment.SetName(name)
            baseSegment.SetColor(color)
            segment = segmentClass(segment=baseSegment, maskKey=maskKey, objectId=objectId)
            segment.path = maskPath
            segment.segmentationNode = instance.segmentationNode
            instance.segments = [segment]
        instance.maskDir = maskDir
        return instance

    @classmethod
    def createEmptySegmentationFromVolumeNode(cls, volumeNode, name, maskDir):
        instance = cls(name, volumeNode=volumeNode, maskDir=maskDir)
        instance.maskDir = maskDir
        return instance

    def populateSegments(self):
        """Populate segments list with newly created ones from segmentation object"""
        baseSegments = [segment.segment for segment in self.segments]
        for i in range(self.segmentationNode.GetSegmentation().GetNumberOfSegments()):
            baseSegment = self.segmentationNode.GetSegmentation().GetNthSegment(i)
            if baseSegment not in baseSegments:
                segment = segmentClass(
                    segment=baseSegment,
                    segmentationNode=self.segmentationNode,
                    name=baseSegment.GetName(),
                    color=baseSegment.GetColor(),
                )
                self.segments.append(segment)

    def markSegmentsForDeletion(self):
        """Mark segment object for deletion and remove it from segments list"""
        segmentationSegments = []
        for i in range(self.segmentationNode.GetSegmentation().GetNumberOfSegments()):
            segmentationSegments.append(self.segmentationNode.GetSegmentation().GetNthSegment(i))
        for segment in self.segments:
            if segment.segment not in segmentationSegments:
                segment.delete = True


class volumeClass:

    def __init__(
        self,
        segmentations: List[segmentationClass] = None,
        maskDir=None,
        availableTagsLayout=None,
        addedTagsLayout=None,
    ):
        if segmentations is None:
            segmentations = []
        self.segmentations = segmentations
        self.tags = []
        self.tagButtons = []
        self.tagsChanged = False
        self.maskDir = maskDir
        self.node = None
        self.name = None
        self.id = None
        self.availableTagsLayout = availableTagsLayout
        self.addedTagsLayout = addedTagsLayout

    def addSegmentation(self, segmentation: segmentationClass):
        self.segmentations.append(segmentation)

    def createSegmentationsOnLoad(self, logic):
        for annClass in logic.projectMeta.obj_classes.items():
            if annClass.geometry_type.name() == "mask_3d":
                segmentation = segmentationClass(annClass.name, self.node, maskDir=self.maskDir)
                self.segmentations.append(segmentation)

    def createSegmentation(self, maskDir, maskKey, name, color, objectId):
        segmentation = segmentationClass.createSegmentationFromFile(
            maskDir, name, color, maskKey, objectId
        )
        self.segmentations.append(segmentation)

    def removeSegmentation(self, segmentationName):
        self.segmentations = [
            segmentation
            for segmentation in self.segmentations
            if segmentation.name != segmentationName
        ]

    def getSegmentationByName(self, segmentationName):
        for segmentation in self.segmentations:
            if segmentation.name == segmentationName:
                return segmentation

    def addToScene(self):
        for segmentation in self.segmentations:
            segmentation.addToScene()

    def removeFromScene(self):
        for segmentation in self.segmentations:
            segmentation.removeFromScene()

    def clear(self):
        for segmentation in self.segmentations:
            segmentation.clear()
        self.segmentations = []
        self.tags = []
        self.node = None
        self.name = None
        self.id = None
        self.maskDir = None
        self.tagButtons = []
        self.tagsChanged = False
        self.deleteAllTagButtons()

    def deleteAllTagButtons(self):
        for layout in [self.availableTagsLayout, self.addedTagsLayout]:
            for i in reversed(range(layout.count())):
                widget = layout.itemAt(i).widget()
                if isinstance(widget, qt.QPushButton):
                    layout.removeWidget(widget)
                    widget.deleteLater()
                    widget = None

    def getSegmentationNames(self):
        return [segmentation.name for segmentation in self.segmentations]

    def assignTag(self, tag):
        self.tags.append(tag)
        self.tagsChanged = True

    def removeTag(self, name, value):
        tag = {"name": name, "value": value}
        self.tags = [t for t in self.tags if t != tag]
        self.tagsChanged = True

    def hasTag(self, name):
        for tag in self.tags:
            if tag["name"] == name:
                return True
        return False

    @classmethod
    def createEmptySegmentationCollection(cls, segmentationNames: List[str], volumeNode):
        return cls([segmentationClass(name, volumeNode) for name in segmentationNames])
