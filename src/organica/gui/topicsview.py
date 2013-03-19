from PyQt4.QtCore import pyqtSignal, Qt
from PyQt4.QtGui import QToolButton, QSortFilterProxyModel, QWidget, QLineEdit, QTreeView, QIcon, QButtonGroup, \
                        QVBoxLayout, QHBoxLayout, QMenu

from organica.gui.selectionmodel import WatchingSelectionModel
from organica.gui.actions import StandardStateValidator, globalCommandManager
from organica.lib.tagsmodel import TagsModel
from organica.lib.filters import TagQuery, Wildcard, replaceInFilters
from organica.utils.extend import globalObjectPool
import organica.gui.resources.qrc_main


TOPICS_VIEW_MODE_GROUP = 'topics_view_mode'
MODE_ICON_SIZE = 32


class _TopicsModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        QSortFilterProxyModel.__init__(self, parent)
        self.setDynamicSortFilter(True)
        self.setSortCaseSensitivity(False)

    def setSourceModel(self, source_model):
        QSortFilterProxyModel.setSourceModel(self, source_model)
        self.sort(1)


class TopicsView(QWidget):
    """Extensible with objects placed in group TOPICS_VIEW_MODE_GROUP.
    Extension objects should obey following protocol:
        icon(size) method - icon that will be placed on button.
        name property - descriptive name of mode.
        tooltip optional property - tooltip that will be displayed on button.
            If does not exists, name will be used instead.
        hierarchy property - hierarchy that will be applied to topic model if
            mode is activated.
    """

    modeChanged = pyqtSignal(object)  # gets mode object as argument
    selectedTagChanged = pyqtSignal(object)  # gets tag identity as argument

    searchFilterHint = 'search_filter'

    def __init__(self, parent, lib):
        QWidget.__init__(self, parent)

        self.__lib = None

        self.searchLine = QLineEdit(self)
        self.searchLine.textChanged.connect(self.__onSearchTextChanged)
        self.searchButton = QToolButton(self)
        self.searchButton.setToolTip('Clear filter')
        self.searchButton.setIcon(QIcon(':/main/images/eraser.png'))
        self.searchButton.setAutoRaise(True)
        self.searchButton.clicked.connect(self.searchLine.clear)
        self.searchButton.clicked.connect(self.searchLine.setFocus)

        self.tree = QTreeView(self)
        self.tree.setSelectionMode(QTreeView.SingleSelection)

        self._treeModel = _TopicsModel()
        self.tree.setModel(self._treeModel)
        self.tree.header().hide()

        selectionModel = WatchingSelectionModel(self._treeModel)
        selectionModel.resetted.connect(self.__onCurrentTagReset)
        selectionModel.currentChanged.connect(self.__onCurrentTagChanged)
        self.tree.setSelectionModel(selectionModel)

        self.modeButtonsGroup = QButtonGroup()

        layout = QVBoxLayout()
        layout.setMargin(0)
        searchBoxLayout = QHBoxLayout()
        searchBoxLayout.addWidget(self.searchLine)
        searchBoxLayout.addWidget(self.searchButton)
        layout.addLayout(searchBoxLayout)
        layout.addWidget(self.tree)
        self.modesLayout = QHBoxLayout()
        layout.addLayout(self.modesLayout)
        self.setLayout(layout)

        self.contextMenu = QMenu(self)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.__showContextMenu)
        self.tree.doubleClicked.connect(self.__onItemDoubleClicked)

        with globalObjectPool().lock:
            self.modes = []
            for mode_object in globalObjectPool().objects(TOPICS_VIEW_MODE_GROUP):
                self.__addMode(mode_object)

            globalObjectPool().objectAdded.connect(self.__addMode)
            globalObjectPool().objectRemoved.connect(self.__removeMode)

        self.lib = lib

    @property
    def lib(self):
        return self.__lib

    @lib.setter
    def lib(self, new_lib):
        """Changing library will reset filter and hierarchy."""
        self.model = TagsModel(new_lib)
        self.model.hierarchy = ['*']
        self._treeModel.setSourceModel(self.model)
        self.tree.hideColumn(0)

    @property
    def activeMode(self):
        checked_button = self.modeButtonsGroup.checkedButton()
        if checked_button is None:
            return None

        for m_object, m_button in self.modes:
            if m_button is checked_button:
                return m_object

    @activeMode.setter
    def activeMode(self, new_mode):
        """Should get mode object or mode name (as returned by object.name)
        """

        for m_object, m_button in self.modes:
            if isinstance(new_mode, str):
                if m_object.name == new_mode:
                    new_mode = m_object
                    mode_button = m_button
                    break
            else:
                if m_object is new_mode:
                    mode_button = m_button
                    break
        else:
            raise TypeError('activeMode.setter should get mode name or existing mode object')

        mode_button.setChecked(True)

    def modeButton(self, mode):
        for m_object, m_button in self.modes:
            if isinstance(mode, str):
                if m_object.name == mode:
                    return m_button
            elif m_object is mode:
                return m_button
        else:
            return None

    @property
    def selectedTag(self):
        return self.tree.currentIndex().data(TagsModel.TagIdentityRole)

    @selectedTag.setter
    def selectedTag(self, new_tag):
        from organica.lib.objects import get_identity
        if get_identity(new_tag) != self.selectedTag:
            indexes = self._treeModel.indexesForTag(get_identity(new_tag))
            if indexes:
                self.setCurrentIndex(indexes[0])

    def __onSearchTextChanged(self, new_search_text):
        tags_model = self._treeModel.sourceModel()
        if tags_model is not None:
            search_filter = TagQuery(value_to_text=Wildcard('*{0}*'.format(new_search_text))) if new_search_text else TagQuery()
            search_filter.hint = self.searchFilterHint
            tags_model.filters = replaceInFilters(tags_model.filters, self.searchFilterHint, search_filter)

    def __addMode(self, mode_object):
        mode_button = QToolButton()
        mode_button.setCheckable(True)
        mode_button.setIcon(mode_object.icon(MODE_ICON_SIZE))
        mode_button.setToolTip(mode_object.tooltip if hasattr(mode_object, 'tooltip') else mode_object.name)
        mode_button.clicked.connect(self.__onModeButtonClicked)
        self.modes.append((mode_object, mode_button))
        self.modeButtonsGroup.addButton(mode_button)
        self.modesLayout.addWidget(mode_button)

    def __removeMode(self, mode_object):
        for m_object, m_button in self.modes:
            if m_object is mode_object:
                m_button.deleteLater()
                break
        self.modes = [x for x in self.modes if x[0] is not mode_object]

    def __onModeButtonClicked(self):
        mode_button = self.sender()

        for m_object, m_button in self.modes:
            if m_button is mode_button:
                self._treeModel.hierarchy = m_object.hierarchy
                self.modeChanged.emit(m_object)

    def __showContextMenu(self, pos):
        if self.lib:
            index = self.tree.indexAt(pos)
            if index.isValid():
                self.contextMenu.popup(self.tree.mapToGlobal(pos))

    def __onItemDoubleClicked(self, index):
        pass

    def __onCurrentTagChanged(self, new_index):
        tag = new_index.data(TagsModel.TagIdentityRole)
        self.selectedTagChanged.emit(tag)

    def __onCurrentTagReset(self):
        self.selectedTagChanged.emit(None)
