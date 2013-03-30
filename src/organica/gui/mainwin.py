import logging
import os
import sys

from PyQt4.QtGui import QMainWindow, QSplitter, QWidget, QIcon, QFileDialog, QMessageBox, QPixmap, \
                        QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QComboBox, QStandardItem, QStandardItemModel
from PyQt4.QtCore import QByteArray, QCoreApplication, QFileInfo, QDir, QUrl, QEvent, Qt, pyqtSignal

from organica.utils.settings import globalQuickSettings, globalSettings
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
        cm.addNewCommand(self.showSettings, 'Workspace.ShowSettings', tr('Settings...'))
        cm.addNewCommand(self.addFiles, 'Library.AddFiles', tr('Add files'), validator='LibraryActive',
                                             default_shortcut='Ctrl+O')
        cm.addNewCommand(self.addDir, 'Library.AddDirectory', tr('Add directory'), validator='LibraryActive')
        cm.addNewCommand(self.showLibraryDatabase, 'Library.ShowDatabase', tr('Show database'), validator='LibraryActive')
        cm.addNewCommand(self.showLibraryProperties, 'Library.ShowProperties', tr('Library properties...'),
                         validator='LibraryActive')
        cm.addNewCommand(self.startSearchCommand, 'Library.Search', tr('Search'), validator='LibraryActive', default_shortcut='Ctrl+F')
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
        self.fileMenu.appendCommand('Workspace.ShowSettings')
        self.fileMenu.appendSeparator()
        self.fileMenu.appendCommand('Application.Exit')
        self.menuBarContainer.appendContainer(self.fileMenu)

        self.libraryMenu.appendCommand('Library.ShowDatabase')
        self.libraryMenu.appendSeparator()
        self.libraryMenu.appendCommand('Library.AddFiles')
        self.libraryMenu.appendCommand('Library.AddDirectory')
        self.libraryMenu.appendSeparator()
        self.libraryMenu.appendCommand('Library.Search')
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
        globalSearchHistoryModel().saveHistory()

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
        environ.lib.setMeta('objectsview_splitter', str(environ.ui.objectsViewSplitter.saveState().toHex(), encoding='ascii'))

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

        ui.splitter = QSplitter(Qt.Horizontal, ui)

        ui.topicsView = TopicsView(ui, environ.lib)
        ui.objectsViewSplitter = QSplitter(Qt.Vertical, ui)

        ui.objectsViewParent = QWidget()
        ui.objectsView = ObjectsView(ui.objectsViewParent, environ.lib)
        ui.searchPanel = SearchPanel(ui.objectsViewParent, environ.lib)
        m_layout = QVBoxLayout(ui.objectsViewParent)
        m_layout.addWidget(ui.objectsView)
        m_layout.addWidget(ui.searchPanel)

        ui.objectsInfoWidgetParent = QWidget()
        ui.objectsViewSplitter.addWidget(ui.objectsViewParent)
        ui.objectsViewSplitter.addWidget(ui.objectsInfoWidgetParent)

        ui.splitter.addWidget(ui.topicsView)
        ui.splitter.addWidget(ui.objectsViewSplitter)

        splitter_state = environ.lib.getMeta('splitterstate')
        if splitter_state:
            ui.splitter.restoreState(QByteArray.fromHex(splitter_state))
        else:
            ui.splitter.setSizes([250, 1000])

        splitter_state = environ.lib.getMeta('objectsview_splitter')
        if splitter_state:
            ui.objectsViewSplitter.restoreState(QByteArray.fromHex(splitter_state))
        else:
            ui.objectsViewSplitter.setSizes([800, 200])

        ui.layout = QVBoxLayout()
        ui.layout.setContentsMargins(0, 0, 0, 0)
        ui.layout.addWidget(ui.splitter)
        ui.setLayout(ui.layout)

        s = globalSettings()

        ui.topicsView.selectedTagChanged.connect(self.__onCurrentTopicChanged)

        quick_search = s['quick_search']
        if not isinstance(quick_search, bool):
            quick_search = True
        ui.searchPanel.quickSearch = quick_search
        ui.searchPanel.searchRequested.connect(self.search)
        ui.searchPanel.hide()

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

        self.endSearch()

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

    def startSearchCommand(self):
        env = self.activeEnviron
        if env is not None:
            if env.ui.searchPanel.isVisible():
                self.endSearch()
            else:
                self.startSearch()

    def startSearch(self, search_text=''):
        env = self.activeEnviron
        if env is not None:
            env.ui.searchPanel.show()
            env.ui.searchPanel.startSearch(search_text)
            env.ui.searchPanel.setFocus()

    def endSearch(self):
        env = self.activeEnviron
        if env is not None and env.ui.searchPanel.isVisible():
            env.ui.searchPanel.endSearch()
            env.ui.searchPanel.hide()

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.NoModifier and event.key() == Qt.Key_Escape:
            if self.activeEnviron is not None and self.activeEnviron.ui.searchPanel.isVisible():
                self.endSearch()
                event.accept()

    objectsSearchHint = 'objects_search_hint'

    def search(self, search_text):
        from organica.lib.filters import NodeQuery, TagQuery, Wildcard

        env = self.activeEnviron
        if env is not None:
            current_node = env.ui.objectsView.currentNode

            if search_text:
                search_text = str(search_text)
                mask = '*{0}*'.format(search_text)
                search_filter = NodeQuery(tags=TagQuery(value_to_text=Wildcard(mask)))
                search_filter = search_filter | NodeQuery(display_name=Wildcard(mask))
            else:
                search_filter = NodeQuery()

            search_filter.hint = self.objectsSearchHint

            objects_model = env.ui.objectsView.model
            objects_model.filters = replaceInFilters(objects_model.filters, self.objectsSearchHint, search_filter)

            env.ui.objectsView.currentNode = current_node

    def showSettings(self):
        from organica.gui.settingsdialog import SettingsDialog

        dialog = SettingsDialog(self)
        dialog.exec_()


_mainWindow = None


def globalMainWindow():
    global _mainWindow
    if not _mainWindow:
        _mainWindow = MainWindow()
    return _mainWindow


class SearchPanel(QWidget):
    searchRequested = pyqtSignal(str)

    def __init__(self, parent, lib):
        QWidget.__init__(self, parent)

        self.quickSearch = True
        self.lib = lib

        self.iconLabel = QLabel(self)
        self.iconLabel.setPixmap(QPixmap(':/main/images/magnifier.png'))

        self.cmbSearch = QComboBox(self)
        self.cmbSearch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.cmbSearch.setEditable(True)
        self.cmbSearch.editTextChanged.connect(self.__onEditTextChanged)

        self.m_layout = QHBoxLayout(self)
        self.m_layout.setContentsMargins(0, 0, 0, 0)
        self.m_layout.addWidget(self.iconLabel)
        self.m_layout.addWidget(self.cmbSearch)

        self.setFocusProxy(self.cmbSearch)
        self.cmbSearch.setModel(globalSearchHistoryModel())
        self.cmbSearch.installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.cmbSearch:
            if event.type() == QEvent.FocusOut:
                globalSearchHistoryModel().addToHistory(self.cmbSearch.currentText())
            elif event.type() == QEvent.KeyPress:
                if event.modifiers() == Qt.NoModifier and event.key() == Qt.Key_Enter:
                    text = self.cmbSearch.currentText()
                    self.searchRequested.emit(text)
                    globalSearchHistoryModel().addToHistory(text)
                    return True
        return QWidget.eventFilter(self, obj, event)

    def __onEditTextChanged(self, search_text):
        if self.quickSearch:
            self.searchRequested.emit(search_text)

    def startSearch(self, search_text=''):
        self.cmbSearch.setCurrentIndex(-1)
        self.cmbSearch.lineEdit().setPlaceholderText(tr('Search'))
        self.cmbSearch.lineEdit().setText(search_text)
        self.cmbSearch.lineEdit().selectAll()

    def endSearch(self):
        globalSearchHistoryModel().addToHistory(self.cmbSearch.currentText())


class SearchHistoryModel(QStandardItemModel):
    def __init__(self):
        QStandardItemModel.__init__(self)

        # load
        qs = globalQuickSettings()

        search_history = qs['search_history']
        if not isinstance(search_history, (tuple, list)):
            search_history = []

        for search_history_item in search_history:
            if isinstance(search_history_item, str):
                self.appendRow(QStandardItem(search_history_item))

    def saveHistory(self):
        qs = globalQuickSettings()

        history = [self.item(row).text() for row in range(self.rowCount())]
        qs['search_history'] = history

    def addToHistory(self, text):
        if not isinstance(text, str):
            raise ValueError('string expected')
        if text and not self.findItems(text):
            self.insertRow(0, QStandardItem(text))


_globalSearchHistoryModel = None


def globalSearchHistoryModel():
    global _globalSearchHistoryModel
    if _globalSearchHistoryModel is None:
        _globalSearchHistoryModel = SearchHistoryModel()
    return _globalSearchHistoryModel
