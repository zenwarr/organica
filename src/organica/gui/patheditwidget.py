from PyQt4.QtGui import QWidget, QHBoxLayout, QLineEdit, QToolButton, QFileDialog
from PyQt4.QtCore import pyqtSignal

from organica.utils.helpers import tr


class PathEditWidget(QWidget):
    pathChanged = pyqtSignal(str)

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)

        self.pathEdit = QLineEdit(self)
        self.pathEdit.textChanged.connect(self.pathChanged)

        self.dialogButton = QToolButton(self)
        self.dialogButton.setText(tr('...'))
        self.dialogButton.clicked.connect(self.showDialog)

        self.fileDialog = QFileDialog(self)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.pathEdit)
        layout.addWidget(self.dialogButton)
        self.setLayout(layout)

    def showDialog(self):
        self.fileDialog.setParent(self)

        if self.fileDialog.exec_() == QFileDialog.Accepted:
            files = self.fileDialog.selectedFiles()
            if files:
                self.pathEdit.setText(files[0])

    @property
    def path(self):
        return self.pathEdit.text()

    @path.setter
    def path(self, new_path):
        self.pathEdit.setText(new_path)
