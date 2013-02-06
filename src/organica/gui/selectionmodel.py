from PyQt4.QtCore import pyqtSignal
from PyQt4.QtGui import QItemSelectionModel


class WatchingSelectionModel(QItemSelectionModel):
    resetted = pyqtSignal()

    def reset(self):
        QItemSelectionModel.reset(self)
        self.resetted.emit()
