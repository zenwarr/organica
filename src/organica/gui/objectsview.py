import logging
from PyQt4.QtCore import Qt, QModelIndex
from PyQt4.QtGui import QWidget, QTreeView, QVBoxLayout, QDesktopServices, QLabel, QListWidget, \
                        QDialogButtonBox, QDialog, QMenu, QAction, QMessageBox
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
            dlg = LocatorChooseDialog(self, locators)
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
            nodes_to_remove = [node.lib.node(node) for node in nodes_to_remove]
            has_managed_files = False
            for node in nodes_to_remove:
                locator_tags = node.tags(TagQuery(value_type=TagValue.TYPE_LOCATOR))
                has_managed_files = any((tag.value.locator.isManagedFile for tag in locator_tags))
                if has_managed_files:
                    break

            msgbox = QMessageBox(self)
            msgbox.setWindowTitle(tr('Delete objects'))
            msgbox.setText(tr('Really delete objects?'))
            msgbox.setIcon(QMessageBox.Question)
            if has_managed_files:
                msgbox.setText(msgbox.text() + tr(' You can also delete files in local storage used by this objects only.'))
            msgbox.setStandardButtons(QMessageBox.Cancel)
            delete_button = msgbox.addButton(tr('Delete'), QMessageBox.AcceptRole)
            delete_with_files_button = None
            if has_managed_files:
                delete_with_files_button = msgbox.addButton(tr('Delete with files'), QMessageBox.AcceptRole)

            msgbox.setDefaultButton(delete_button)

            msgbox.exec_()
            clicked_button = msgbox.clickedButton()
            if clicked_button is msgbox.button(QMessageBox.Cancel):
                return

            files_to_remove = []
            if clicked_button is delete_with_files_button:
                def can_delete(locator):
                    if locator.isManagedFile and locator.lib and locator.lib.storage is not None:
                        return len(locator.lib.storage.referredNodes(locator)) == 1

                locators = list()
                for node in nodes_to_remove:
                    locators += node.tags(TagQuery(valueType=TagValue.TYPE_LOCATOR))
                    files_to_remove += [loc for loc in locators if can_delete(loc)]


class LocatorChooseDialog(Dialog):
    def __init__(self, parent, locators):
        Dialog.__init__(self, parent, name='locator_choose_dialog')
        self.locators = locators

        self.setWindowTitle(tr('Select locator to use'))

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setText(tr('This node has several locators linked. Choose one you want to use:'))

        self.list = QListWidget(self)
        for locator in self.locators:
            self.list.addItem(locator.launchUrl.toString())

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
