import logging
import os
from typing import Literal

import qt
import slicer


class InputDialog(qt.QDialog):
    def __init__(
        self,
        parent=None,
        options=None,
        validate: Literal["number"] = None,
        icon=None,
        title=None,
        label=None,
    ):
        super(InputDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~qt.Qt.WindowContextHelpButtonHint)
        self.vlayout = qt.QVBoxLayout(self)
        if label:
            self.label = qt.QLabel(label, self)
            self.vlayout.addWidget(self.label)
        self.button = qt.QPushButton("Save", self)
        if not options:
            self.line_edit = qt.QLineEdit(self)
            self.button.clicked.connect(self.save_and_close_line)
            self.vlayout.addWidget(self.line_edit)
        else:
            self.combo_box = qt.QComboBox(self)
            self.combo_box.addItems(options)
            self.button.clicked.connect(self.save_and_close_combo)
            self.vlayout.addWidget(self.combo_box)
        self.vlayout.addWidget(self.button)
        self.validate = validate

        if icon:
            self.setWindowIcon(icon)
        if title:
            title = title.replace("    ➡️", "")
            self.setWindowTitle(title)

        self.adjustSize()
        self.move(qt.QCursor.pos())

    def save_and_close_line(self):
        self.user_input = self.line_edit.text
        if self.validate == "number":
            try:
                int(self.user_input)
            except ValueError:
                slicer.util.errorDisplay("Please enter a number")
                return
        self.accept()

    def save_and_close_combo(self):
        self.user_input = self.combo_box.currentText
        self.accept()

    def execute_and_assign_tag(self, text, replace_str, newButton, logic):
        if self.exec_():
            userInput = self.user_input
            if ": NUM" in text:
                userInput = int(userInput)
            tag = {"name": text.split(replace_str)[0], "value": userInput}
            if not logic.volume.hasTag(tag["name"]):
                newButton.setText(text.replace(replace_str, f": {userInput}    🗑️"))
                logic.volume.assignTag(tag)
                return True
            else:
                self.show_notification(f"Tag [{tag['name']}] already exists.", 2000)
                return False
        else:
            return False

    def show_notification(self, message, duration=2000):
        logging.debug(f"Notification shown: {message}")
        msg = qt.QMessageBox(self)
        msg.setText(message)
        msg.setWindowTitle("Notification")
        qt.QTimer.singleShot(duration, msg.close)
        msg.exec_()

    @staticmethod
    def show_notification_none(icon, message, duration=2000):
        logging.debug(f"Notification shown: {message}")
        msg = qt.QMessageBox()
        msg.setText(message)
        msg.setWindowIcon(icon)
        msg.setWindowTitle("Notification")
        msg.move(qt.QCursor.pos())
        qt.QTimer.singleShot(duration, msg.close)
        msg.exec_()


class SuperviselyDialog(qt.QDialog):
    def __init__(
        self,
        message,
        type: Literal["info", "error", "confirm", "delay"] = "info",
        delay: int = 3000,
        parent=None,
    ):
        """Create a dialog with a message and a button.

        Parameters
        ----------
        message : str
            The message to be displayed.
        type : Literal["info", "error", "confirm", "delay"], optional
            The type of the dialog, by default "info".
        delay : int, optional
            The delay in milliseconds before the dialog closes, by default 3000.
        parent : qt.QWidget, optional
            The parent widget, by default None.
        """
        super(SuperviselyDialog, self).__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~qt.Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Information")
        if type == "error":
            self.setWindowTitle("Error")
        elif type == "confirm":
            self.setWindowTitle("Confirmation")
        elif type == "delay":
            qt.QTimer.singleShot(delay, self.close)
        moduleDir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        iconPath = os.path.join(moduleDir, "Resources", "Icons", "supervisely.svg")
        self.setWindowIcon(qt.QIcon(iconPath))
        layout = qt.QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        message = message.replace("\n", "<br>")
        self.label = qt.QLabel(message)
        self.label.setTextFormat(qt.Qt.RichText)
        self.label.setTextInteractionFlags(qt.Qt.TextBrowserInteraction)
        self.label.setOpenExternalLinks(True)
        layout.addWidget(self.label)
        buttonLayout = qt.QHBoxLayout()
        buttonLayout.addItem(
            qt.QSpacerItem(20, 40, qt.QSizePolicy.Expanding, qt.QSizePolicy.Minimum)
        )
        if type != "delay":
            if type == "confirm":
                self.button = qt.QPushButton("Yes")
                self.button.clicked.connect(self.on_ok_clicked)
                buttonLayout.addWidget(self.button)
                self.cancelButton = qt.QPushButton("No")
                self.cancelButton.clicked.connect(self.on_cancel_clicked)
                buttonLayout.addWidget(self.cancelButton)
            else:
                self.button = qt.QPushButton("OK")
                self.button.clicked.connect(self.on_ok_clicked)
                buttonLayout.addWidget(self.button)
            layout.addLayout(buttonLayout)

        self.setLayout(layout)

        self.adjustSize()
        self.exec_()

    def on_ok_clicked(self):
        self.decision = True
        self.close()

    def on_cancel_clicked(self):
        self.decision = False
        self.close()

    def return_decision(self):
        return self.decision

    def __bool__(self):
        return self.return_decision()


def block_widget(widget, text: str = None):
    if text is None:
        text = "The module could not be loaded because <a href='https://pypi.org/project/supervisely/'>Supervisely</a> package is not installed."
    errorLabel = qt.QLabel(text)
    errorLabel.setTextFormat(qt.Qt.RichText)
    errorLabel.setTextInteractionFlags(qt.Qt.TextBrowserInteraction)
    errorLabel.setOpenExternalLinks(True)
    errorLabel.setStyleSheet("border: 4px solid black; font-size: 14px; ")
    errorLabel.setAlignment(qt.Qt.AlignCenter)
    while widget.layout.count():
        child = widget.layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()
    widget.layout.addWidget(errorLabel)
