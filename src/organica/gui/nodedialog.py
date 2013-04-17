import logging
import os
import copy

from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDialog, QListView, QTabWidget, QDialogButtonBox, QStandardItemModel, \
                        QLineEdit, QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QWidget, QStandardItem, QIcon

from organica.utils.helpers import tr, removeLastSlash, first
from organica.utils.extend import globalObjectPool
from organica.utils.settings import globalQuickSettings
from organica.gui.dialog import Dialog


logger = logging.getLogger(__name__)


NodeEditorProviderGroup = 'node_editor_provider'


class NodeEditDialog(Dialog):
    """Dialog used when new objects are added to library or existing ones are edited. It
    allows user to edit one or more nodes of one library.
    """

    class _EditorData(object):
        def __init__(self):
            self.widget = None
            self.generator = None

    def __init__(self, parent, lib, nodes):
        Dialog.__init__(self, parent, name='node_edit_dialog')

        self.lib = lib
        self.__nodes = []  # list of available Nodes objects
        self.__editors = []  # contains _EditorData objects
        self.__currentEditor = None  # _EditorData for active editor
        self.autoFlush = True  # if true, nodes will be flushed by dialog on pressing OK
        self.__selectedIndexes = []  # indexes for nodes selected in top-left list
        self.__nodesLoaded = False

        self.setWindowTitle(tr('Edit nodes'))

        # list that will display all nodes loaded into dialog
        self.nodeList = QListView(self)
        self.nodeList.setMaximumWidth(200)
        self.nodeList.setSelectionMode(QListView.ExtendedSelection)

        # model for list above
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
        self.noEditorsLabel.setText(tr('You have no editor extensions applicable'))
        self.noEditorsLabel.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

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
        self.tabsEditors.currentChanged.connect(self.__onCurrentEditorChanged)

        with globalObjectPool().lock:
            # discover already registered editors
            for prov in globalObjectPool().objects(group=NodeEditorProviderGroup):
                # check profile affinity
                if not hasattr(prov, 'profileUuid') or prov.profileUuid == self.lib.profileUuid:
                    try:
                        self.addEditorFromProvider(prov)
                    except Exception as err:
                        logger.error('failed to create editor from provider: ' + str(err))

            if not self.__editors:
                self.__showNoEditorsPage()

            # we can add editors on-the-fly
            globalObjectPool().objectAdded.connect(self.__onObjectAdded)
            globalObjectPool().objectRemoved.connect(self.__onObjectRemoved)

        self.__setNodes(nodes)

    def addEditorFromProvider(self, provider):
        """Add editor from extension object that should have NodeEditorProviderGroup.
        If profile affinity does not allow editor to be shown on this library, no error raised.
        """

        if provider is None or not hasattr(provider, 'group') or provider.group != NodeEditorProviderGroup:
            raise TypeError('invalid argument: provider')

        # if we already have this provider added, switch to its tab
        existing_editor = first(ed for ed in self.__editors if ed.provider is provider)
        if existing_editor is not None:
            self.tabsEditors.setCurrentWidget(existing_editor.widget)
            return

        if not hasattr(provider, 'create') or not callable(provider.create):
            raise TypeError('provider should have "create" method')

        # create editor
        try:
            editor_widget = provider.create(self.lib)
        except Exception as err:
            raise TypeError('provider failed to create editor: {0}'.format(err))

        if not isinstance(editor_widget, QWidget) or not all((hasattr(editor_widget, aname) for aname in ('load', 'getModified', 'reset'))):
            raise TypeError('node editor does not support required interface')

        # if we have 'no editors' label, remove it
        if not self.__editors and self.tabsEditors.count():
            self.noEditorsLabel.hide()
            self.tabsEditors.removeTab(0)

        editor_data = self._EditorData()
        editor_data.widget = editor_widget
        editor_data.provider = provider
        self.__editors.append(editor_data)

        editor_icon = editor_widget.icon if hasattr(editor_widget, 'icon') else None
        editor_title = editor_widget.title if hasattr(editor_widget, 'title') else 'Unknown'
        self.tabsEditors.addTab(editor_widget, editor_icon or QIcon(), editor_title)

    @property
    def nodes(self):
        self.__save()
        return copy.deepcopy(self.__nodes)

    def reject(self):
        self.__save()
        Dialog.reject(self)

    def accept(self):
        """Flushes changes made in library only if autoFlush flag is set."""
        self.__save()
        if self.autoFlush:
            self.flush()
        Dialog.accept(self)

    def __setNodes(self, new_nodes):
        """It does not save changes made in loaded nodes."""
        from organica.lib.filters import TagQuery

        # clear old ones
        self.__nodes = []
        self.nodesModel.clear()

        # and fill model with new data
        last_unk_id = 0
        for node in new_nodes:
            item = QStandardItem()

            # get text that will be displayed in list. Do not use display name, but locator instead.
            locators = node.resources
            if not locators:
                if node.isFlushed:
                    # if object is flushed, display its id (it is better than nothing)
                    item.setText('#{0}'.format(node.id))
                else:
                    # so... we have no information for this node. Lets give id to it.
                    last_unk_id += 1
                    item.setText(tr('<element {0}>').format(last_unk_id))
            else:
                # take first locator and use it. If we have sourceUrl defined, use it instead.
                choosen_locator = locators[0].getResolved(node)
                if choosen_locator.source:
                    if choosen_locator.source.isLocalFile:
                        filepath = removeLastSlash(choosen_locator.source.localFilePath)
                        item.setText(os.path.basename(filepath))
                    else:
                        item.setText(choosen_locator.source.url.toString())
                elif choosen_locator.isLocalFile:
                    full_filename = removeLastSlash(choosen_locator.localFilePath)
                    item.setText(os.path.basename(full_filename))
                else:
                    item.setText(choosen_locator.url.toString())
                item.setIcon(choosen_locator.icon)

            node_copy = copy.deepcopy(node)
            item.setEditable(False)
            self.nodesModel.appendRow(item)
            self.__nodes.append(node_copy)

        if self.nodesModel.rowCount():
            self.nodeList.setCurrentIndex(self.nodesModel.index(0, 0))

    def __onObjectAdded(self, new_object):
        # should we add another editor?
        if new_object.group == NodeEditorProviderGroup and \
                    (not hasattr(new_object, 'profileUuid') or new_object.profileUuid == self.lib.profileUuid):
            self.addEditorFromProvider(new_object)

    def __onObjectRemoved(self, removed_object):
        if removed_object is None or removed_object.group != NodeEditorProviderGroup:
            return

        editor_data = first(ed for ed in self.__editors if ed.provider is removed_object)
        if editor_data is not None:
            self.tabsEditors.removeTab(self.tabsEditors.indexOf(editor_data.widget))
            self.__editors = [ed for ed in self.__editors if ed.provider is not removed_object]
            if not self.__editors:
                self.__showNoEditorsPage()

    def __onCurrentEditorChanged(self, new_editor_index):
        # save changes old editor has made
        self.__save()

        if new_editor_index != -1:
            editor_widget = self.tabsEditors.widget(new_editor_index)
            if editor_widget is not self.noEditorsLabel:
                self.__currentEditor = first(ed for ed in self.__editors if ed.widget is editor_widget)
                if self.__currentEditor is not None:
                    self.__load()
                    return
        self.__currentEditor = None

    def __save(self):
        """Saves information editor has made to all selected nodes. Use this method when
        current editor changes or when set of selected nodes is altered.
        """
        single_node_edited = len(self.__selectedIndexes) == 1
        for selected_node_index in self.__selectedIndexes:
            node = self.__nodes[selected_node_index.row()]

            # save display name
            if single_node_edited or self.chkCommonDisplayName.isChecked():
                node.displayNameTemplate = self.txtDisplayName.text()

            if self.__currentEditor is not None:
                try:
                    self.__nodes[selected_node_index.row()] = self.__currentEditor.widget.getModified(node)
                except Exception as err:
                    logger.error('node editor failed to save changes: {0}'.format(err))

    def __load(self):
        """Loads information in active editor."""
        self.__nodesLoaded = False
        self.__selectedIndexes = self.nodeList.selectedIndexes()
        nodes = self.selectedNodes

        self.txtDisplayName.clear()

        self.chkCommonDisplayName.setEnabled(bool(nodes))

        self.chkCommonDisplayName.setChecked(len(nodes) == 1)
        self.chkCommonDisplayName.setVisible(len(nodes) > 1)
        self.txtDisplayName.setEnabled(len(nodes) <= 1)

        if nodes:
            self.txtDisplayName.setText(nodes[0].displayNameTemplate)

        if self.__currentEditor is not None:
            self.__currentEditor.widget.setEnabled(bool(nodes))
            if nodes:
                try:
                    self.__currentEditor.widget.load(nodes)
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

    def flush(self):
        from organica.lib.objects import TagValue
        from organica.lib.storage import LocalStorage
        from organica.utils.operations import globalOperationContext, WrapperOperation, globalOperationPool

        resources_to_move = []
        for node in self.__nodes:
            node.flush(self.lib)
            for tag in node.allTags:
                if tag.valueType == TagValue.TYPE_LOCATOR and tag.value.locator.source:
                    resources_to_move.append((node, tag))

        def moveResources(resources_to_move):
            progress_part = 100.0 / len(resources_to_move)
            for node, tag in resources_to_move:
                source_filename = tag.value.locator.source.localFilePath
                target_filename = tag.value.locator.localFilePath
                with globalOperationContext().newOperation('adding {0}'.format(source_filename),
                                                           progress_weight=progress_part):
                    if not tag.value.locator.source.isLocalFile or not tag.value.locator.isLocalFile:
                        globalOperationContext().currentOperation.addMessage(tr('Storage supports only file source and target'),
                                                                             logging.ERROR)
                        continue
                    node.lib.storage.addFile(source_filename, target_filename)

        if resources_to_move:
            WrapperOperation(lambda: moveResources(resources_to_move)).run(WrapperOperation.RUNMODE_THIS_THREAD)

    @property
    def selectedNodes(self):
        return [self.__nodes[index.row()] for index in self.__selectedIndexes]
