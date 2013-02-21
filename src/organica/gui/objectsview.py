import logging
from PyQt4.QtCore import Qt, QModelIndex
from PyQt4.QtGui import QWidget, QTreeView, QVBoxLayout, QDesktopServices, QLabel, QListWidget, \
                        QDialogButtonBox, QDialog
from organica.lib.objectsmodel import ObjectsModel
from organica.gui.selectionmodel import WatchingSelectionModel
from organica.gui.actions import globalCommandManager
from organica.utils.helpers import tr


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

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.view)

        #todo: create context menu
        #todo: create actions (here or in other place)

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
        index = self.view.indexAt(position)
        if index.isValid():
            node = index.data(ObjectsModel.NodeIdentityRole)
            if node is not None:
                self.contextMenu.popup(self.view.mapToGlobal(position))

    def launch(self, item):
        """Launches given QModelIndex or Node in associated system application"""

        if isinstance(item, QModelIndex):
            item = item.data(ObjectsModel.NodeIdentityRole)

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

    def edit(self):
        ###WARN: this code will not work for objects from different libraries!!!
        """Starts edit dialog for all selected nodes and flushes changes"""
        from organica.gui.nodedialog import NodeEditDialog

        nodes = [index.data(ObjectsModel.NodeIdentityRole) for index in self.view.selectionModel().selectedRows()]
        if nodes:
            lib = nodes[0]
            dlg = NodeEditDialog(self, lib, nodes)
            if dlg.exec_() != NodeEditDialog.Accepted:
                return

            for modified_node in dlg.nodes:
                modified_node.flush()


class LocatorChooseDialog(QDialog):
    def __init__(self, parent, locators):
        QDialog.__init__(self, parent)
        self.locators = locators

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setText(tr('This node has several locators linked. Choose one you want to use'))

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
