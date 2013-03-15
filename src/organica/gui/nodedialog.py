import logging
import os
import copy

from PyQt4.QtCore import Qt, QByteArray, QUrl
from PyQt4.QtGui import QDialog, QListView, QTabWidget, QDialogButtonBox, QStandardItemModel, \
                        QLineEdit, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QWidget, QStandardItem, QIcon

from organica.utils.helpers import tr, removeLastSlash
from organica.utils.extend import globalObjectPool
from organica.utils.settings import globalQuickSettings


logger = logging.getLogger(__name__)


NODE_EDITOR_PROVIDER_GROUP = 'node_editor_provider'


class NodeEditDialog(QDialog):
    """Dialog used when new objects are added to library or existing ones are edited. It
    allows user to edit one or more nodes of one library.
    """

    def __init__(self, parent, lib, nodes):
        QDialog.__init__(self, parent)

        self.lib = lib
        self.__nodes = []
        self.__editors = []  # contains tuples of (editor, generator)
        self.__currentEditor = None
        self.__nodesLoaded = True
        self.autoFlush = True  # if true, nodes will be flushed by dialog on pressing OK
        self.__selectedIndexes = []

        self.setWindowTitle(tr('Edit nodes'))

        # create widgets

        # list that will display all nodes loaded into dialog
        self.nodeList = QListView(self)
        self.nodeList.setMaximumWidth(200)
        self.nodeList.setSelectionMode(QListView.ExtendedSelection)

        # model for above list
        self.nodesModel = QStandardItemModel()
        self.nodeList.setModel(self.nodesModel)

        # check box can be checked to modify display names of selected objects at once
        self.chkCommonDisplayName = QCheckBox(self)

        # line edit for display name
        self.txtDisplayName = QLineEdit(self)
        self.chkCommonDisplayName.toggled.connect(self.txtDisplayName.setEnabled)

        # allows user to switch between different editors
        self.tabsEditors = QTabWidget(self)

        # label displayed when no editors are loaded into dialog
        self.noEditorsLabel = QLabel(self)
        self.noEditorsLabel.hide()
        self.noEditorsLabel.setText(tr('You have no editor extensions appliable'))
        self.noEditorsLabel.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)

        displayNameLayout = QHBoxLayout()
        displayNameLayout.addWidget(self.chkCommonDisplayName)
        displayNameLayout.addWidget(self.txtDisplayName)

        nodeEditLayout = QVBoxLayout()
        nodeEditLayout.addLayout(displayNameLayout)
        nodeEditLayout.addWidget(self.tabsEditors)

        nodesLayout = QHBoxLayout()
        nodesLayout.addWidget(self.nodeList)
        nodesLayout.addLayout(nodeEditLayout)

        layout = QVBoxLayout(self)
        layout.addLayout(nodesLayout)
        layout.addWidget(self.buttonBox)

        self.nodeList.selectionModel().selectionChanged.connect(self.__onSelectionChanged)
        self.tabsEditors.currentChanged.connect(self.__onEditorChanged)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        with globalObjectPool().lock:
            # discover already registered editors
            for prov in globalObjectPool().objects(group=NODE_EDITOR_PROVIDER_GROUP):
                # check profile affinity
                if not hasattr(prov, 'profileUuid') or prov.profileUuid == self.lib.profileUuid:
                    self.addEditor(prov)

            if not self.__editors:
                self.__showNoEditorsPage()

            # we can add editors on-the-fly
            globalObjectPool().objectAdded.connect(self.__onObjectAdded)
            globalObjectPool().objectRemoved.connect(self.__onObjectRemoved)

        # restore saved dialog geometry
        qs = globalQuickSettings()
        geom = qs['nodeEditor_geometry']
        if geom:
            self.restoreGeometry(QByteArray.fromHex(geom))

        self.__setNodes(nodes)

    def closeEvent(self, close_event):
        # save dialog geometry
        qs = globalQuickSettings()
        qs['nodeEditor_geometry'] = str(self.saveGeometry().toHex(), encoding='ascii')

    def addEditor(self, provider):
        """Add editor from extension object that should have NODE_EDITOR_PROVIDER_GROUP.
        If profile affinity does not allow editor to be shown on this library, no error raised.
        """

        if provider is None or not hasattr(provider, 'group') or provider.group != NODE_EDITOR_PROVIDER_GROUP:
            raise TypeError('invalid argument: provider')

        # if we already have this provider added, switch to its tab
        for editor_data in self.__editors:
            if editor_data[1] is provider:
                self.tabsEditors.setCurrentIndex(self.tabsEditors.indexOf(editor_data[0]))
                return

        if not hasattr(provider, 'create') or not callable(provider.create):
            logger.error('provider should have "create" method')
            return

        # create editor
        try:
            editor = provider.create(self.lib)
        except Exception as err:
            logger.error('provider failed to create editor: {0}'.format(err))
            return

        if not isinstance(editor, QWidget) or not all((hasattr(editor, aname) for aname in ('load', 'getModified', 'reset'))):
            logger.error('node editor does not support required interface')
            return

        # if we have 'no editors' label, remove it
        if not self.__editors and self.tabsEditors.count():
            self.noEditorsLabel.hide()
            self.tabsEditors.removeTab(0)

        editor_icon = editor.icon if hasattr(editor, 'icon') else None
        editor_title = editor.title if hasattr(editor, 'title') else 'Unknown'
        self.tabsEditors.addTab(editor, editor_icon or QIcon(), editor_title)
        self.__editors.append((editor, provider))

    @property
    def nodes(self):
        self.__save()
        return copy.deepcopy(self.__nodes)

    def reject(self):
        self.__save()
        QDialog.reject(self)

    def accept(self):
        """Flushes changes made in library.
        """
        self.__save()
        if self.autoFlush:
            for node in self.__nodes:
                node.flush(self.lib)
        QDialog.accept(self)

    def __setNodes(self, new_nodes):
        """It does not save changes made in loaded nodes.
        """

        from organica.lib.filters import TagQuery

        # clear old ones
        self.__nodes = []
        self.nodesModel.clear()

        # and fill model with new data
        last_unk_id = 0
        for node in new_nodes:
            item = QStandardItem()

            # get text that will be displayed in list. Do not use display name, but locator instead.
            locators = [tag.value.locator for tag in node.tags(TagQuery(tag_class='locator'))]
            if not locators:
                if node.isFlushed:
                    # if object is flushed, display its id (it is better than nothing)
                    item.setText('#{0}'.format(node.id))
                else:
                    # so... we have no information for this node. Lets give id to it.
                    last_unk_id += 1
                    item.setText(tr('<element {0}>').format(last_unk_id))
            else:
                # take first locator and use it
                if locators[0].isLocalFile:
                    full_filename = removeLastSlash(locators[0].localFilePath)
                    item.setText(os.path.basename(full_filename))
                else:
                    item.setText(locators[0].url)
                item.setIcon(locators[0].icon)

            node_copy = copy.deepcopy(node)
            item.setData(node_copy, Qt.UserRole)
            item.setEditable(False)
            self.nodesModel.appendRow(item)
            self.__nodes.append(node_copy)

        if self.nodesModel.rowCount():
            self.nodeList.setCurrentIndex(self.nodesModel.index(0, 0))

    def __onObjectAdded(self, new_object):
        # should we add another editor?
        if new_object.group == NODE_EDITOR_PROVIDER_GROUP and \
                    (not hasattr(new_object, 'profileUuid') or new_object.profile == self.lib.profileUuid):
            self.addEditor(new_object)

    def __onObjectRemoved(self, removed_object):
        if removed_object is None or removed_object.group != NODE_EDITOR_PROVIDER_GROUP:
            return

        for d in self.__editors:
            if d[1] is removed_object:
                self.tabsEditors.removeTab(self.tabsEditors.indexOf(d[0]))
                self.__editors = [x for x in self.__editors if x[1] is not removed_object]
                if not self.__editors:
                    self.__showNoEditorsPage()
                break

    def __onEditorChanged(self, new_editor_index):
        # we should save changes old editor has made
        self.__save()

        if new_editor_index != -1:
            editor = self.tabsEditors.widget(new_editor_index)
            self.__currentEditor = editor
            if editor is not None and editor is not self.noEditorsLabel:
                # we should save information old editor has changed
                self.__load()
        else:
            self.__currentEditor = None

    def __save(self):
        """Saves information editor has made to all selected nodes. Use this method when
        current editor changes or when set of selected nodes is altered.
        """
        single_node_edited = len(self.__selectedIndexes) == 1
        for selected_node_index in self.__selectedIndexes:
            node = selected_node_index.data(Qt.UserRole)

            # save display name
            if single_node_edited or self.chkCommonDisplayName.isChecked():
                node.displayNameTemplate = self.txtDisplayName.text()

            if self.__currentEditor is not None:
                try:
                    self.__nodes[selected_node_index.row()] = self.__currentEditor.getModified(node)
                except Exception as err:
                    logger.error('node editor failed to save changes: {0}'.format(err))

    def __load(self):
        """Loads information in active editor.
        """
        self.__nodesLoaded = False
        self.__selectedIndexes = self.nodeList.selectedIndexes()
        nodes = [index.data(Qt.UserRole) for index in self.__selectedIndexes]

        self.txtDisplayName.clear()

        self.chkCommonDisplayName.setEnabled(bool(nodes))

        self.chkCommonDisplayName.setChecked(len(nodes) == 1)
        self.chkCommonDisplayName.setVisible(len(nodes) > 1)
        self.txtDisplayName.setEnabled(len(nodes) <= 1)

        if nodes:
            self.txtDisplayName.setText(nodes[0].displayNameTemplate)

        if self.__currentEditor is not None:
            self.__currentEditor.setEnabled(bool(nodes))
            if nodes:
                try:
                    self.__currentEditor.load(nodes)
                    self.__nodesLoaded = True
                except Exception as err:
                    logger.error('node editor failed to load nodes: {0}'.format(err))
            else:
                try:
                    self.__currentEditor.reset()
                except Exception as err:
                    logger.error('node editor failed to reset: {0}'.format(err))

    def __showNoEditorsPage(self):
        if not self.__editors and not self.tabsEditors.count():
            self.tabsEditors.addTab(self.noEditorsLabel, tr('Message'))
            self.noEditorsLabel.show()
            self.tabsEditors.setCurrentIndex(self.tabsEditors.indexOf(self.noEditorsLabel))

    def __onSelectionChanged(self, selected, deselected):
        if self.__nodesLoaded:
            self.__save()
        self.__load()
