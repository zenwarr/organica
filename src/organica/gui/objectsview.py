import logging
import copy
from PyQt4.QtCore import Qt, QModelIndex, QUrl
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
        self.view.doubleClicked.connect(self.launch)

        selection_model = WatchingSelectionModel(self.model)
        selection_model.selectionChanged.connect(self.__onSelectionChanged)
        selection_model.resetted.connect(self.__onSelectionResetted)
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

    def __onSelectionChanged(self, selected, deselected):
        cm = globalCommandManager()
        rows_count = len(self.view.selectionModel().selectedRows())
        cm.activate('Objects.OneObjectActive', rows_count == 1)
        cm.activate('Objects.ObjectsActive', rows_count)

    def __onSelectionResetted(self):
        cm = globalCommandManager()
        cm.deactivate('Objects.OneObjectActive')
        cm.deactivate('Objects.ObjectsActive')

    def __showContextMenu(self, position):
        if hasattr(self, 'contextMenu'):
            index = self.view.indexAt(position)
            if index.isValid():
                node = index.data(ObjectsModel.NodeIdentityRole)
                if node is not None:
                    self.contextMenu.popup(self.view.mapToGlobal(position))

    def launch(self, item):
        """Launches given QModelIndex or Node in associated system application"""

        if isinstance(item, QModelIndex):
            item = item.data(ObjectsModel.NodeIdentityRole)
            item = item.lib.node(item)

        if item is None:
            return

        from organica.lib.filters import TagQuery
        locators = [tag.value.locator for tag in item.tags(TagQuery(tag_class='locator'))]

        if not locators:
            logger.debug('no locators for node #{0}'.format(item.id))
            return
        elif len(locators) > 1:
            # let user to choose locator
            dlg = LocatorChooseDialog(self, locators, item)
            if dlg.exec_() != LocatorChooseDialog.Accepted:
                return
            url = dlg.selectedLocator.launchUrl
        else:
            url = locators[0].launchUrl

        QDesktopServices.openUrl(url)

    def editSelected(self):
        ###WARN: this code will not work for objects from different libraries!!!
        """Starts edit dialog for all selected nodes and flushes changes"""
        from organica.gui.nodedialog import NodeEditDialog

        idents = [index.data(ObjectsModel.NodeIdentityRole) for index in self.view.selectionModel().selectedRows()]
        if idents:
            lib = idents[0].lib
            dlg = NodeEditDialog(self, lib, [lib.node(ident) for ident in idents])
            if dlg.exec_() != NodeEditDialog.Accepted:
                return

    def removeSelected(self):
        from organica.lib.filters import TagQuery
        from organica.lib.objects import TagValue

        nodes_to_remove = [index.data(ObjectsModel.NodeIdentityRole) for index in self.view.selectionModel().selectedRows()]
        if nodes_to_remove:
            if QMessageBox.question(self, tr('Delete objects'), tr('Do you want to delete selected objects?'),
                                    QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
                for node in nodes_to_remove:
                    if node is not None:
                        node.lib.removeNode(node)

    @property
    def currentNode(self):
        return self.view.currentIndex().data(ObjectsModel.NodeIdentityRole)

    @currentNode.setter
    def currentNode(self, new_node):
        if new_node is not None:
            index = self.model.indexOfNode(new_node) or QModelIndex()
        else:
            index = QModelIndex()
        self.view.setCurrentIndex(index)


class LocatorChooseDialog(Dialog):
    def __init__(self, parent, locators, node):
        Dialog.__init__(self, parent, name='locator_choose_dialog')
        self.locators = locators
        self.node = copy.deepcopy(node)

        self.setWindowTitle(tr('Select locator to use'))

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setText(tr('This node has several locators linked. Choose one you want to use:'))

        self.list = QListWidget(self)
        for locator in self.locators:
            launch_url = locator.launchUrl.toLocalFile() if locator.launchUrl.isLocalFile() else locator.launchUrl.toString()
            item = QListWidgetItem(locator.icon, launch_url)
            if locator.broken:
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
    def selectedLocator(self):
        sel_index = self.list.currentRow()
        if 0 <= sel_index < len(self.locators):
            return self.locators[sel_index]
        else:
            return None
