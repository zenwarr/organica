import logging
import copy
from PyQt4.QtCore import Qt, QModelIndex
from PyQt4.QtGui import QWidget, QTreeView, QVBoxLayout, QDesktopServices, QLabel, QListWidget, QListWidgetItem, \
                        QDialogButtonBox, QDialog, QMenu, QAction, QMessageBox, QBrush
from organica.lib.objectsmodel import ObjectsModel
from organica.gui.selectionmodel import WatchingSelectionModel
from organica.gui.actions import globalCommandManager
from organica.utils.helpers import tr
from organica.gui.dialog import Dialog


logger = logging.getLogger(__name__)


class ObjectsView(QWidget):
    def __init__(self, parent, lib=None):
        QWidget.__init__(self, parent)

        self.view = QTreeView(self)
        self.view.setSelectionMode(QTreeView.ExtendedSelection)
        self.view.setSelectionBehavior(QTreeView.SelectRows)
        self.view.setRootIsDecorated(False)

        self.model = ObjectsModel(lib)
        self.view.setModel(self.model)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.__showContextMenu)
        self.view.activated.connect(self.launch)

        selection_model = WatchingSelectionModel(self.model)
        selection_model.selectionChanged.connect(self.__onSelectionChanged)
        selection_model.resetted.connect(self.__onSelectionChanged)
        self.view.setSelectionModel(selection_model)

        self.contextMenu = QMenu(self)
        edit_action = QAction(tr('Edit objects'), self)
        edit_action.triggered.connect(self.editSelected)
        self.contextMenu.addAction(edit_action)
        self.contextMenu.addSeparator()
        remove_action = QAction(tr('Remove objects'), self)
        remove_action.triggered.connect(self.removeSelected)
        self.contextMenu.addAction(remove_action)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.view)

    @property
    def lib(self):
        return self.model.lib

    def __onSelectionChanged(self, selected=QModelIndex(), deselected=QModelIndex()):
        cm = globalCommandManager()
        rows_count = len(self.view.selectionModel().selectedRows())
        cm.activate('Objects.OneObjectActive', rows_count == 1)
        cm.activate('Objects.ObjectsActive', rows_count)

    def __showContextMenu(self, position):
        index = self.view.indexAt(position)
        if index.isValid():
            node = index.data(ObjectsModel.NodeIdentityRole)
            if node is not None:
                self.contextMenu.popup(self.view.mapToGlobal(position))

    def launch(self, item):
        """Launches given QModelIndex or Node in associated system application"""

        if isinstance(item, QModelIndex):
            node = item.data(ObjectsModel.NodeIdentityRole)
            node = node.lib.node(node)
        else:
            node = item

        if node is None:
            return

        resources = node.resources

        if not resources:
            logger.debug('no associated resources for node #{0}'.format(node.id))
            return
        elif len(resources) > 1:
            # let user to choose resource
            dlg = LocatorChooseDialog(self, resources, node)
            if dlg.exec_() != LocatorChooseDialog.Accepted:
                return
            url = dlg.selectedResource.getResolved(node).url
        else:
            url = resources[0].getResolved(node).url

        QDesktopServices.openUrl(url)

    def editSelected(self):
        """Starts edit dialog for all selected nodes and flushes changes"""
        from organica.gui.nodedialog import NodeEditDialog

        idents = [index.data(ObjectsModel.NodeIdentityRole) for index in self.view.selectionModel().selectedRows()]
        if idents:
            lib = idents[0].lib
            dlg = NodeEditDialog(self, lib, [lib.node(ident) for ident in idents])
            dlg.exec_()

    def removeSelected(self):
        nodes_to_remove = [index.data(ObjectsModel.NodeIdentityRole) for index in self.view.selectionModel().selectedRows()]
        if nodes_to_remove:
            if QMessageBox.question(self, tr('Delete objects'), tr('Do you want to delete selected objects?'),
                                    QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                for node in nodes_to_remove:
                    if node is not None:
                        node.lib.removeNode(node)

    @property
    def currentNode(self):
        """Returns Identity of current node"""
        return self.view.currentIndex().data(ObjectsModel.NodeIdentityRole)

    @currentNode.setter
    def currentNode(self, new_node):
        if new_node is not None:
            index = self.model.indexOfNode(new_node) or QModelIndex()
        else:
            index = QModelIndex()
        self.view.setCurrentIndex(index)


class LocatorChooseDialog(Dialog):
    def __init__(self, parent, resources, node):
        Dialog.__init__(self, parent, name='locator_choose_dialog')
        self.resources = resources
        self.node = copy.deepcopy(node)

        self.setWindowTitle(tr('Select resource to use'))

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setText(tr('This node has several resources linked. Choose one you want to use:'))

        self.list = QListWidget(self)
        for resource in self.resources:
            resolved = resource.getResolved(node)
            item = QListWidgetItem(resource.icon, str(resolved))
            if resolved.broken:
                item.setForeground(QBrush(Qt.red))
            self.list.addItem(item)
        self.list.itemActivated.connect(self.accept)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.list)
        self.layout.addWidget(self.buttonBox)

    @property
    def selectedResource(self):
        sel_index = self.list.currentRow()
        if 0 <= sel_index < len(self.resources):
            return self.resources[sel_index]
        else:
            return None
