import copy
from PyQt4.QtCore import Qt, QAbstractItemModel, QModelIndex
from PyQt4.QtGui import QWidget, QTreeView, QToolButton, QHBoxLayout, QVBoxLayout, QDialog, QMessageBox, QLineEdit, \
                        QFormLayout, QDialogButtonBox
from organica.generic.extension import GENERIC_EXTENSION_UUID
from organica.lib.objects import Node, Tag, TagValue
from organica.utils.helpers import cicompare, tr
from organica.gui.dialog import Dialog


class GenericNodeEditorProvider(object):
    group = 'node_editor_provider'
    extensionUuid = GENERIC_EXTENSION_UUID

    def create(self, lib):
        return GenericNodeEditor(lib)


class GenericNodeEditor(QWidget):
    def __init__(self, lib, parent=None):
        QWidget.__init__(self, parent)
        self.lib = lib

        self.tagTree = QTreeView(self)
        self.tagsModel = GenericTagsModel(lib)
        self.tagTree.setModel(self.tagsModel)

        self.btnAddTag = QToolButton(self)
        self.btnAddTag.setText(tr('Add tag'))
        self.btnAddTag.clicked.connect(self.addTag)

        self.btnRemoveTag = QToolButton(self)
        self.btnRemoveTag.setText(tr('Remove tag'))
        self.btnRemoveTag.clicked.connect(self.removeTag)

        self.buttonsLayout = QHBoxLayout()
        self.buttonsLayout.addWidget(self.btnAddTag)
        self.buttonsLayout.addStretch()
        self.buttonsLayout.addWidget(self.btnRemoveTag)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.tagTree)
        self.layout.addLayout(self.buttonsLayout)

        self.originalCommonTags = []

    def load(self, nodes):
        self.originalCommonTags = [copy.deepcopy(tag) for tag in Node.commonTags(nodes)]
        self.tagsModel.load(self.originalCommonTags)
        self.tagTree.expandAll()

    def getModified(self, original_node):
        node_tags = [tag for tag in original_node.allTags if tag not in self.originalCommonTags] + self.tagsModel.tags
        original_node.allTags = node_tags
        return original_node

    def reset(self):
        self.tagsModel.load([])

    def addTag(self):
        """Brings dialog to enter name/value of new tag and then adds new tag to list"""
        dlg = AddTagDialog(self, self.lib)
        if dlg.exec_() == AddTagDialog.Accepted:
            new_index = self.tagsModel.addTag(dlg.className, dlg.tagValue)
            if new_index is not None and new_index.isValid():
                self.tagTree.setCurrentIndex(new_index)

    def removeTag(self):
        """Removes tag that is currently selected in tree"""
        self.tagsModel.remove(self.tagTree.currentIndex())


class GenericTagsModel(QAbstractItemModel):
    _TOPLEVEL_GROUP_INDEX = 4294967295  # 2**32 - 1

    class TagGroup(object):
        def __init__(self, name, tags):
            self.name = name
            self.tags = tags

    def __init__(self, lib):
        QAbstractItemModel.__init__(self)
        self.__groups = []
        self.lib = lib

    def load(self, tags):
        """Load list of tags into model"""
        self.__groups = []

        groups = dict()
        for tag in tags:
            tag_copy = copy.deepcopy(tag)
            if tag.className in groups:
                groups[tag.className].append(tag_copy)
            else:
                groups[tag.className] = [tag_copy]

        for class_name in groups.keys():
            self.__groups.append(GenericTagsModel.TagGroup(class_name, groups[class_name]))

        self.reset()

    @property
    def tags(self):
        result = []
        for group in self.__groups:
            result += group.tags
        return result

    def flags(self, index):
        if not index.isValid() or (index.internalId() == self._TOPLEVEL_GROUP_INDEX and index.column() == 1):
            return Qt.ItemIsEnabled
        elif index.internalId() != self._TOPLEVEL_GROUP_INDEX and index.column() == 0:
            return Qt.ItemIsEnabled
        else:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def index(self, row, column, parent=QModelIndex()):
        if not parent.isValid():
            if 0 <= row < len(self.__groups):
                return self.createIndex(row, column, self._TOPLEVEL_GROUP_INDEX)
        elif parent.internalId() == self._TOPLEVEL_GROUP_INDEX and parent.column() == 0:
            if 0 <= row < len(self.__groups[parent.row()].tags):
                return self.createIndex(row, column, parent.row())
        return QModelIndex()

    def parent(self, index):
        if not index.isValid() or index.internalId() == self._TOPLEVEL_GROUP_INDEX:
            return QModelIndex()
        else:
            return self.createIndex(index.internalId(), 0, self._TOPLEVEL_GROUP_INDEX)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        if index.internalId() == self._TOPLEVEL_GROUP_INDEX:
            if index.column() == 0:
                if role in (Qt.DisplayRole, Qt.EditRole):
                    return self.__groups[index.row()].name
        else:
            group_index = index.internalId()
            if (0 <= group_index < len(self.__groups)) and (0 <= index.row() <
                            len(self.__groups[group_index].tags)) and index.column() == 1:
                if role in (Qt.DisplayRole, Qt.EditRole):
                    return str(self.__groups[group_index].tags[index.row()].value)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                if section == 0:
                    return tr('Class name')
                elif section == 1:
                    return tr('Value')
        return None

    def rowCount(self, index=QModelIndex()):
        if not index.isValid():
            return len(self.__groups)
        elif index.internalId() == self._TOPLEVEL_GROUP_INDEX and index.column() == 0:
            if 0 <= index.row() < len(self.__groups):
                return len(self.__groups[index.row()].tags)
        return 0

    def columnCount(self, index=QModelIndex()):
        return 2 if (not index.isValid() or (index.internalId() == self._TOPLEVEL_GROUP_INDEX and index.column() == 0)) else 0

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or role == Qt.EditRole:
            return False

        # first case - change group name
        if index.internalId() == self._TOPLEVEL_GROUP_INDEX and index.column() == 0:
            old_group_name = self.__groups[index.row()].name
            if old_group_name == value:
                return True

            group_index = 0
            # if we already have another group with this name, join it
            for group in self.__groups:
                if group.name == value:
                    # add only tags from group user renamed that are not in another group
                    tags_to_add = [tag for tag in self.__groups[index.row()].tags if tag not in group.tags]

                    if tags_to_add:
                        self.beginInsertRows(self.createIndex(group_index, 0, self._TOPLEVEL_GROUP_INDEX), len(group.tags),
                                             len(group.tags) + len(tags_to_add))
                        group.tags += tags_to_add
                        self.endInsertRows()

                    # remove old (renamed) group
                    self.beginRemoveRows(QModelIndex(), index.row(), index.row())
                    del self.__groups[index.row()]
                    self.endRemoveRows()
                    return True

                group_index += 1
        elif (0 <= index.internalId() < len(self.__groups) and index.column() == 1):
            if not (0 <= index.row() < len(self.__groups[index.internalId()].tags)):
                return False

            group = self.__groups[index.internalId()]
            if group.tags[index.row()].value == value:
                return True

            # change tag value. If we have tag with same name and value, fail
            from organica.lib.filters import TagQuery

            q = TagQuery(tag_class=group.name, value=value)
            if any(q.passes(tag) for tag in group.tags):
                return False

            group[index.row()].value = value
            return True

        return False

    def addTag(self, class_name, tag_value):
        """Adds new tag to model and returns index of this tag."""

        # we should find group index for this tag. If group does not exist, create it
        group_index = 0
        for group in self.__groups:
            if cicompare(group.name, class_name):
                break
            group_index += 1
        else:
            self.beginInsertRows(QModelIndex(), len(self.__groups), len(self.__groups))
            self.__groups.append(GenericTagsModel.TagGroup(class_name, []))
            group_index = len(self.__groups) - 1
            self.endInsertRows()

        group = self.__groups[group_index]

        # check if have duplicated tag in this group
        from organica.lib.filters import TagQuery

        q = TagQuery(tag_class=class_name, value=tag_value)
        if any(q.passes(tag) for tag in group.tags):
            return QModelIndex()

        self.beginInsertRows(self.createIndex(group_index, 0, self._TOPLEVEL_GROUP_INDEX), len(group.tags), len(group.tags))
        group.tags.append(Tag(self.lib.tagClass(class_name), tag_value))
        self.endInsertRows()

    def remove(self, index):
        if not index or not index.isValid():
            return

        # we can remove entire group!
        if index.internalId() == self._TOPLEVEL_GROUP_INDEX and index.column() == 0:
            self.beginRemoveRows(QModelIndex(), index.row(), index.row())
            del self.__groups[index.row()]
            self.endRemoveRows()
        elif index.internalId() != self._TOPLEVEL_GROUP_INDEX and index.column() == 1:
            self.beginRemoveRows(self.createIndex(index.internalId(), 0, self._TOPLEVEL_GROUP_INDEX), index.row(), index.row())
            del self.__groups[index.internalId()].tags[index.row()]
            self.endRemoveRows()


class AddTagDialog(Dialog):
    def __init__(self, parent, lib):
        Dialog.__init__(self, parent, name='generic_add_tag_dialog')
        self.lib = lib

        self.setWindowTitle(tr('Add tag'))

        self.txtClassName = QLineEdit(self)
        self.txtValue = QLineEdit(self)
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.layout = QVBoxLayout(self)

        formLayout = QFormLayout()
        formLayout.addRow(tr('Class name'), self.txtClassName)
        formLayout.addRow(tr('Value'), self.txtValue)

        self.layout.addLayout(formLayout)
        self.layout.addWidget(self.buttonBox)

    @property
    def className(self):
        return self.txtClassName.text()

    @property
    def tagValue(self):
        return TagValue(self.txtValue.text())

    def accept(self):
        if not self.lib.tagClass(self.txtClassName.text()):
            QMessageBox.information(self, tr('Error'), tr('No tag class {0} in current library!' \
                            .format(self.txtClassName.text())))
        else:
            QDialog.accept(self)
