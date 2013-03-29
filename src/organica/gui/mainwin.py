import logging
import os
import sys

from PyQt4.QtGui import QMainWindow, QSplitter, QWidget, QIcon, QFileDialog, QMessageBox, \
                        QTabWidget, QVBoxLayout
from PyQt4.QtCore import QByteArray, QCoreApplication, QFileInfo, QDir, QUrl

from organica.utils.settings import globalQuickSettings
import organica.gui.resources.qrc_main  # resource initialization
from organica.gui.topicsview import TopicsView
from organica.gui.objectsview import ObjectsView
from organica.gui.actions import globalCommandManager, QMenuBarCommandContainer, QMenuCommandContainer, \
                        StandardStateValidator
from organica.utils.helpers import tr, removeLastSlash, lastFileDialogPath, setLastFileDialogPath
from organica.gui.aboutdialog import AboutDialog
from organica.gui.profiles import getProfile, genericProfile
from organica.lib.library import Library
from organica.gui.createlibrarywizard import CreateLibraryWizard
from organica.lib.storage import LocalStorage
from organica.lib.filters import replaceInFilters


class LibraryEnvironment(object):
    def __init__(self):
        self.lib = None
        self.profile = None
        self.ui = None


LIBRARY_DIALOG_FILTER = 'Organica libraries (*.orl);;All files (*.*)'
logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    objectsViewFilterHint = 'topic_filter'

    def __init__(self):
        QMainWindow.__init__(self)

        self.setWindowIcon(QIcon(':/main/images/application.png'))

        self.libTabWidget = QTabWidget(self)
        self.libTabWidget.currentChanged.connect(self.__onLibTabIndexChanged)
        self.libTabWidget.tabCloseRequested.connect(self.__onLibTabCloseRequested)
        self.libTabWidget.setTabsClosable(True)
        self.setCentralWidget(self.libTabWidget)

        self.workspace = []  # list of LibraryEnvironment objects
        self.__activeEnviron = None  # LibraryEnvironment object

        cm = globalCommandManager()

        self.libraryActiveValidator = StandardStateValidator('LibraryActive')
        self.libraryActiveValidator.isActive = False
        cm.addValidator(self.libraryActiveValidator)

        cm.addNewCommand(self.loadLibrary, 'Workspace.LoadLibrary', tr('Load library'),
                                             default_shortcut='Ctrl+Shift+O')
        cm.addNewCommand(self.createLibrary, 'Workspace.CreateLibrary', tr('Create library'),
                                             default_shortcut='Ctrl+Shift+N')
        cm.addNewCommand(self.closeActiveEnviron, 'Workspace.CloseActiveLibrary', tr('Close library'),
                                             default_shortcut='Ctrl+Shift+W', validator='LibraryActive')
        cm.addNewCommand(self.addFiles, 'Library.AddFiles', tr('Add files'), validator='LibraryActive',
                                             default_shortcut='Ctrl+O')
        cm.addNewCommand(self.addDir, 'Library.AddDirectory', tr('Add directory'), validator='LibraryActive')
        cm.addNewCommand(self.showLibraryDatabase, 'Library.ShowDatabase', tr('Show database'), validator='LibraryActive')
        cm.addNewCommand(self.showLibraryProperties, 'Library.ShowProperties', tr('Library properties...'),
                         validator='LibraryActive')
        cm.addNewCommand(self.close, 'Application.Exit', tr('Exit'))
        cm.addNewCommand(self.showAbout, 'Application.ShowAbout', tr('About...'))

        self.menuBarContainer = QMenuBarCommandContainer('MainMenuBar', self)
        cm.addContainer(self.menuBarContainer)

        self.fileMenu = QMenuCommandContainer('FileMenu', tr('File'), self)
        cm.addContainer(self.fileMenu)

        self.libraryMenu = QMenuCommandContainer('LibraryMenu', tr('Library'), self)
        cm.addContainer(self.libraryMenu)

        self.fileMenu.appendCommand('Workspace.LoadLibrary')
        self.fileMenu.appendCommand('Workspace.CreateLibrary')
        self.fileMenu.appendCommand('Workspace.CloseActiveLibrary')
        self.fileMenu.appendSeparator()
        self.fileMenu.appendCommand('Application.Exit')
        self.menuBarContainer.appendContainer(self.fileMenu)

        self.libraryMenu.appendCommand('Library.ShowDatabase')
        self.libraryMenu.appendSeparator()
        self.libraryMenu.appendCommand('Library.AddFiles')
        self.libraryMenu.appendCommand('Library.AddDirectory')
        self.libraryMenu.appendSeparator()
        self.libraryMenu.appendCommand('Library.ShowProperties')
        self.menuBarContainer.appendContainer(self.libraryMenu)

        self.helpMenu = QMenuCommandContainer('Help', tr('Help'), self)
        cm.addContainer(self.helpMenu)

        self.helpMenu.appendCommand('Application.ShowAbout')
        self.menuBarContainer.appendContainer(self.helpMenu)

        self.setMenuBar(self.menuBarContainer)

        self.updateTitle()

        qs = globalQuickSettings()
        geom = qs['mainWindow_geometry']
        if geom and isinstance(geom, str):
            self.restoreGeometry(QByteArray.fromHex(geom))
        state = qs['mainWindow_state']
        if state and isinstance(geom, str):
            self.restoreState(QByteArray.fromHex(state))

        # restore saved workspace
        saved_workspace = qs['saved_workspace']
        if saved_workspace and isinstance(saved_workspace, (list, tuple)):
            for lib_path in saved_workspace:
                self.loadLibraryFromFile(lib_path)

        saved_active_lib_index = qs['saved_active_lib_index']
        if isinstance(saved_active_lib_index, int) and (0 <= saved_active_lib_index < len(saved_workspace)):
            for environ in self.workspace:
                # we use QFileInfo instead of os.path.samefile because last one fails when path does not exists
                if QFileInfo(environ.lib.databaseFilename) == QFileInfo(saved_workspace[saved_active_lib_index]):
                    self.libTabWidget.setCurrentWidget(environ.ui)
                    break
            else:
                self.libTabWidget.setCurrentIndex(0)

    def closeEvent(self, closeEvent):
        # save workspace to be restored on next launch
        qs = globalQuickSettings()
        qs['saved_workspace'] = [env.lib.databaseFilename for env in self.workspace]
        qs['saved_active_lib_index'] = self.libTabWidget.currentIndex()

        while self.workspace:
            self.closeEnviron(self.workspace[0])

        qs['mainWindow_geometry'] = str(self.saveGeometry().toHex(), encoding='ascii')
        qs['mainWindow_state'] = str(self.saveState().toHex(), encoding='ascii')

    def updateTitle(self):
        if self.activeEnviron is not None:
            self.setWindowTitle('{0} - Organica'.format(self.getTitleForEnviron(self.activeEnviron)))
        else:
            self.setWindowTitle('Organica')

    def loadLibrary(self):
        filename = QFileDialog.getOpenFileName(self, QCoreApplication.applicationName(), lastFileDialogPath(), LIBRARY_DIALOG_FILTER)
        if filename:
            setLastFileDialogPath(filename)
            self.loadLibraryFromFile(filename)

    def loadLibraryFromFile(self, filename):
        if not QDir.isAbsolutePath(filename):
            filename = QFileInfo(filename).absoluteFilePath()
        filename = QDir.toNativeSeparators(filename)

        env_of_duplicate = [env for env in self.workspace if env.lib is not None \
                             and QFileInfo(env.lib.databaseFilename) == QFileInfo(filename)]
        if env_of_duplicate:
            self.activeEnviron = env_of_duplicate[0]
            return

        newenv = None

        try:
            newlib = Library.loadLibrary(filename)

            # try to load library
            profile_uuid = newlib.getMeta('profile')
            if not profile_uuid:
                logger.warn('no profile associated with library {0}, falling back to generic'.format(filename))
                profile = genericProfile()
            else:
                profile = getProfile(profile_uuid)
                if profile is None:
                    logger.warn('no profile extension {0} installed for library {1}, falling back to generic' \
                                .format(profile_uuid, filename))
                    profile = genericProfile()

            if profile is None:
                raise Exception('failed to load library {0}: cannot find profile to load it'.format(filename))

            newenv = LibraryEnvironment()
            newenv.lib = newlib
            newenv.profile = profile
            newenv.ui = self.createUiForEnviron(newenv)
            self.libTabWidget.addTab(newenv.ui, self.getTitleForEnviron(newenv))

            self.workspace.append(newenv)

            if hasattr(newenv.profile, 'createProfileEnviron'):
                newenv.profileEnviron = profile.createProfileEnviron(newenv)
        except Exception as err:
            self.reportError('failed to load library from file {0}: {1}'.format(filename, err))

        if newenv is not None:
            self.activeEnviron = newenv

    @property
    def activeEnviron(self):
        widget = self.libTabWidget.currentWidget()
        r = [env for env in self.workspace if env.ui == widget]
        return r[0] if r else None

    @activeEnviron.setter
    def activeEnviron(self, environ):
        if environ is not None and environ.ui is not None:
            self.libTabWidget.setCurrentWidget(environ.ui)

    def createLibrary(self):
        wizard = CreateLibraryWizard(self)
        if wizard.exec_() != CreateLibraryWizard.Accepted:
            return

        #todo: check if database already used

        try:
            newlib = wizard.lib
        except Exception as err:
            self.reportError(tr('failed to create library: {0}').format(err))
        else:
            self.loadLibraryFromFile(newlib.databaseFilename)

    def closeEnviron(self, environ):
        # unload profile
        if environ is None:
            return

        # save gui state
        environ.lib.setMeta('splitterstate', str(environ.ui.splitter.saveState().toHex(), encoding='ascii'))

        if environ.profile is not None:
            if environ.profileEnviron is not None and hasattr(environ.profileEnviron, 'onUnload'):
                environ.profileEnviron.onUnload()

        self.workspace = [env for env in self.workspace if env is not environ]

        tab_index = self.libTabWidget.indexOf(environ.ui)
        self.libTabWidget.removeTab(tab_index)
        environ.ui.deleteLater()

        #todo: we should ensure that no other operations using this library
        environ.lib.close()

    def closeActiveEnviron(self):
        if self.activeEnviron is not None:
            self.closeEnviron(self.activeEnviron)

    def showAbout(self):
        about_dialog = AboutDialog(self)
        about_dialog.exec_()

    def reportError(self, text):
        logger.error(text)
        QMessageBox.critical(self, tr('Error'), text)

    def createUiForEnviron(self, environ):
        ui = QWidget(self)

        ui.splitter = QSplitter(ui)

        ui.topicsView = TopicsView(ui, environ.lib)
        ui.objectsView = ObjectsView(ui, environ.lib)

        ui.splitter.addWidget(ui.topicsView)
        ui.splitter.addWidget(ui.objectsView)

        splitter_state = environ.lib.getMeta('splitterstate')
        if splitter_state:
            ui.splitter.restoreState(QByteArray.fromHex(splitter_state))
        else:
            ui.splitter.setSizes([250, 1000])

        ui.layout = QVBoxLayout()
        ui.layout.setContentsMargins(0, 0, 0, 0)
        ui.layout.addWidget(ui.splitter)
        ui.setLayout(ui.layout)

        ui.topicsView.selectedTagChanged.connect(self.__onCurrentTopicChanged)

        return ui

    def getTitleForEnviron(self, environ):
        if environ.lib is not None:
            if environ.lib.name:
                title = environ.lib.name
            else:
                title = '<{0}>'.format(QFileInfo(environ.lib.databaseFilename).fileName())

            if environ.profile is not None:
                title += ' [{0}]'.format(environ.profile.name)
        elif environ.profile is not None:
            title = '[{0}]'.format(environ.profile.name)
        else:
            title = ''
        return title

    def environFromTab(self, tab):
        if isinstance(tab, int):
            tab = self.libTabWidget.widget(tab)
        r = [env for env in self.workspace if env.ui is tab]
        return r[0] if r else None

    def __onLibTabIndexChanged(self, new_index):
        self.updateTitle()
        self.libraryActiveValidator.isActive = bool(new_index >= 0)

    def __onLibTabCloseRequested(self, tab_index):
        environ = self.environFromTab(tab_index)
        if environ is not None:
            self.closeEnviron(environ)

    def createNodeFromUrl(self, display_name, url, environ):
        if environ is not None and environ.lib is not None:
            environ.lib.createNode(display_name, url)

    def addFiles(self):
        if self.activeEnviron is not None:
            dialog = QFileDialog(self, tr('Add files to library'), lastFileDialogPath())
            dialog.setFileMode(QFileDialog.ExistingFiles)
            if dialog.exec_() == QFileDialog.Accepted:
                setLastFileDialogPath(dialog.selectedFiles()[0])
                self.addFilesFromList(dialog.selectedFiles())

    def addDir(self):
        if self.activeEnviron is not None:
            dialog = QFileDialog(self, tr('Add directory with contents to library'), lastFileDialogPath())
            dialog.setFileMode(QFileDialog.Directory)
            if dialog.exec_() == QFileDialog.Accepted:
                setLastFileDialogPath(dialog.selectedFiles()[0])
                self.addFilesFromList([dialog.selectedFiles()[0]])

    def addFilesFromList(self, filenames):
        from organica.lib.objects import Node, Identity, Tag
        from organica.lib.locator import Locator
        from organica.gui.nodedialog import NodeEditDialog
        from organica.lib.formatstring import FormatString

        env = self.activeEnviron
        if env is not None and env.lib is not None:
            nodes = []
            for filename in filenames:
                node = Node()
                node.identity = Identity(env.lib)

                locator_class = env.lib.tagClass('locator')
                if locator_class:
                    default_locator = None
                    if env.lib.storage is not None and env.lib.storage.pathTemplate:
                        default_locator = Locator.fromManagedFile(env.lib.storage.getStoragePath(filename, node),
                                                                  env.lib, QUrl.fromLocalFile(filename))
                    if not default_locator:
                        default_locator = Locator.fromLocalFile(filename)

                    node.link(Tag(env.lib.tagClass('locator'), default_locator))
                nodes.append(node)

            nodeEditDialog = NodeEditDialog(self, env.lib, nodes)
            nodeEditDialog.autoFlush = True
            nodeEditDialog.exec_()

    def showLibraryDatabase(self):
        from organica.gui.databasewidget import DatabaseDialog

        env = self.activeEnviron
        if env is not None and env.lib is not None:
            if sys.platform.startswith('win32'):
                # show built-in dialog
                database_dialog = DatabaseDialog(env.lib.connection, self)
                database_dialog.exec_()
            else:
                # requires sqlitebrowser package to be installed
                os.system('sqlitebrowser "{0}" &'.format(env.lib.databaseFilename))

    def __onCurrentTopicChanged(self, new_tag_ident):
        from organica.lib.filters import NodeQuery, TagQuery

        for env in self.workspace:
            if env.ui.topicsView is self.sender():
                environ = env
                break
        else:
            return

        objects_model = environ.ui.objectsView.model

        topic_filter = NodeQuery(tags=TagQuery(identity=new_tag_ident)) if new_tag_ident is not None else NodeQuery()
        topic_filter.hint = self.objectsViewFilterHint
        objects_model.filters = replaceInFilters(objects_model.filters, self.objectsViewFilterHint, topic_filter)

    def showLibraryProperties(self):
        from organica.gui.librarypropertiesdialog import LibraryPropertiesDialog

        env = self.activeEnviron
        if env is not None:
            dialog = LibraryPropertiesDialog(self, env.lib)
            if dialog.exec_() == LibraryPropertiesDialog.Accepted:
                # library parameters can be changed - update it
                lib_filename = env.lib.databaseFilename
                self.closeEnviron(env)
                self.loadLibraryFromFile(lib_filename)


_mainWindow = None


def globalMainWindow():
    global _mainWindow
    if not _mainWindow:
        _mainWindow = MainWindow()
    return _mainWindow
