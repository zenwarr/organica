from PyQt4.QtGui import *
from PyQt4.QtCore import *

from organica.utils.settings import globalQuickSettings
import organica.gui.resources.qrc_main  # resource initialization
from organica.gui.topicsview import TopicsView


class _LibraryEnv(object):
    def __init__(self):
        self.lib = None
        self.profile = None


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)

        self.setAcceptDrops(True)
        self.setWindowIcon(QIcon(':/main/images/application.png'))

        qs = globalQuickSettings()

        self.splitter = QSplitter(self)
        self.topicsView = TopicsView(self)
        self.splitter.addWidget(self.topicsView)
        self.splitter.addWidget(QWidget(self))
        splitter_state = qs['mainWindow/splitter']
        if splitter_state:
            self.splitter.restoreState(QByteArray(splitter_state))
        self.setCentralWidget(self.splitter)

        self.workspace = []  # list of _LibraryEnv objects
        self.activeLibraryEnv = None  # _LibraryEnv object

        self.statusBar().showMessage('Hello, World!')
        self.updateTitle()

        geom = qs['mainWindow/geometry']
        if geom is not None:
            self.restoreGeometry(geom)
        state = qs['mainWindow/state']
        if state is not None:
            self.restoreState(state)

    def closeEvent(self, closeEvent):
        qs = globalQuickSettings()
        qs['mainWindow/geometry'] = self.saveGeometry()
        qs['mainWindow/state'] = self.saveState()
        qs['mainWindow/splitter'] = self.splitter.saveState()

    def updateTitle(self):
        self.setWindowTitle('Organica')

    def loadLibrary(self):
        pass

    def loadLibraryFromFile(self, filename):
        pass

    def createLibrary(self):
        pass

    def createLibraryInFile(self, filename, profile):
        pass

    def closeActiveLibrary(self):
        pass


_mainWindow = None


def globalMainWindow():
    global _mainWindow
    if not _mainWindow:
        _mainWindow = MainWindow()
    return _mainWindow
