import copy
from PyQt4.QtCore import Qt, QAbstractItemModel, QModelIndex, pyqtSignal, QSize
from PyQt4.QtGui import QWidget, QTableView, QToolButton, QHBoxLayout, QVBoxLayout, QDialog, QMessageBox, QLineEdit, \
                        QFormLayout, QDialogButtonBox, QComboBox, QSizePolicy, QCheckBox, QValidator, QLabel, \
                        QItemDelegate
from organica.generic.extension import GENERIC_EXTENSION_UUID
from organica.lib.objects import Node, Tag, TagValue
from organica.utils.helpers import cicompare, tr, setWidgetTabOrder
from organica.gui.dialog import Dialog
from organica.lib.tagclassesmodel import TagClassesModel
from organica.generic.valueeditwidget import ValueEditWidget


class GenericNodeEditorProvider(object):
    group = 'node_editor_provider'
    extensionUuid = GENERIC_EXTENSION_UUID

    def create(self, lib):
        return GenericNodeEditor(lib)


class GenericNodeEditor(QWidget):
    dataChanged = pyqtSignal()

    def __init__(self, lib, parent=None):
        QWidget.__init__(self, parent)
        self.lib = lib

        self.tagsTable = QTableView(self)
        self.tagsTable.setWordWrap(False)
        self.tagsTable.setCornerButtonEnabled(False)
        self.tagsTable.setSelectionBehavior(QTableView.SelectRows)
        self.tagsTable.setSelectionMode(QTableView.ExtendedSelection)
        self.tagsTable.verticalHeader().setDefaultSectionSize(20)
        self.tagsTable.verticalHeader().hide()
        self.tagsTable.horizontalHeader().setStretchLastSection(True)

        self.tagsModel = GenericTagsModel(lib)
        self.tagsTable.setModel(self.tagsModel)

        self.btnAddTag = QToolButton(self)
        self.btnAddTag.setText(tr('Add'))
        self.btnAddTag.clicked.connect(self.addTag)

        self.btnRemoveTag = QToolButton(self)
        self.btnRemoveTag.setText(tr('Remove'))
        self.btnRemoveTag.clicked.connect(self.removeTag)

        self.buttonsLayout = QHBoxLayout()
        self.buttonsLayout.addWidget(self.btnAddTag)
        self.buttonsLayout.addStretch()
        self.buttonsLayout.addWidget(self.btnRemoveTag)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.tagsTable)
        self.layout.addLayout(self.buttonsLayout)

        self.originalCommonTags = []

        class TagClassDelegate(QItemDelegate):
            def createEditor(self, parent, option, index):
                model = index.model()
                if model is None or not hasattr(model, 'lib'):
                    raise ValueError('TagClassDelegate cannot be used with models that do not have "lib" attribute')
                widget = QComboBox(parent)
                widget.setModel(TagClassesModel(model.lib))
                widget.setModelColumn(0)
                return widget

            def setEditorData(self, editor, index):
                editor.setCurrentIndex(editor.model().classIndex(index.data(GenericTagsModel.TagClassRole)).row())

            def setModelData(self, editor, model, index):
                current_class = editor.model().index(editor.currentIndex(), 0).data(TagClassesModel.TagClassIdentityRole)
                lib = index.model().lib
                model.setData(index, lib.tagClass(current_class))

            def sizeHint(self, option, index):
                return QSize(-1, 20)

        class TagValueDelegate(QItemDelegate):
            def createEditor(self, parent, option, index):
                model = index.model()
                if model is None or not hasattr(model, 'lib'):
                    raise ValueError('TagValueDelegate cannot be used with models that do not have "lib" attribute')
                return ValueEditWidget(parent, model.lib, compact_layout=True)

            def setEditorData(self, editor, index):
                editor.value = index.data(Qt.EditRole)

            def setModelData(self, editor, model, index):
                model.setData(index, editor.value, Qt.EditRole)

            def sizeHint(self, option, index):
                return QSize(-1, 20)

        # we should hold references to delegates to prevent Python GC from deleting objects (as view does not own
        # delegates we set)
        self._first_delegate = TagClassDelegate()
        self._second_delegate = TagValueDelegate()

        self.tagsTable.setItemDelegateForColumn(0, self._first_delegate)
        self.tagsTable.setItemDelegateForColumn(1, self._second_delegate)

    def load(self, nodes):
        self.originalCommonTags = [copy.deepcopy(tag) for tag in Node.commonTags(nodes)]
        self.tagsModel.tags = self.originalCommonTags

    def getModified(self, original_node):
        node_tags = [copy.deepcopy(tag) for tag in original_node.allTags if tag not in self.originalCommonTags] + self.tagsModel.tags
        node = copy.deepcopy(original_node)
        node.allTags = node_tags
        return node

    def reset(self):
        self.tagsModel.tags = []

    def addTag(self):
        """Brings dialog to enter name/value of new tag and then adds new tag to list"""
        dlg = AddTagDialog(self, self.lib)
        current_class = self.tagsTable.currentIndex().data(GenericTagsModel.TagClassRole)
        if current_class is not None:
            dlg.tagClass = current_class
        if dlg.exec_() == AddTagDialog.Accepted:
            new_index = self.tagsModel.addTag(Tag(dlg.tagClass, dlg.tagValue))
            if new_index is not None and new_index.isValid():
                self.tagsTable.setCurrentIndex(new_index)
            self.dataChanged.emit()

    def removeTag(self):
        self.tagsModel.removeTags([index.data(GenericTagsModel.TagRole) for index in self.tagsTable.selectionModel().selectedRows()])
        self.dataChanged.emit()


class GenericTagsModel(QAbstractItemModel):
    TagClassRole = Qt.UserRole + 200
    TagRole = Qt.UserRole + 201

    def __init__(self, lib):
        QAbstractItemModel.__init__(self)
        self.lib = lib
        self.__tags = []

    @property
    def tags(self):
        return copy.deepcopy(self.__tags)

    @tags.setter
    def tags(self, new_tags):
        self.beginResetModel()
        self.__tags = new_tags
        self.endResetModel()

    def flags(self, index):
        return Qt.ItemIsSelectable|Qt.ItemIsEnabled|Qt.ItemIsEditable

    def index(self, row, column, parent):
        return self.createIndex(row, column) if self.hasIndex(row, column, parent) else QModelIndex()

    def parent(self, index):
        return QModelIndex()

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.__tags)):
            return None
        tag = self.__tags[index.row()]
        if role == Qt.DisplayRole:
            if index.column() == 0:
                return tag.tagClass.name
            elif index.column() == 1:
                return str(tag.value)
        elif role == Qt.EditRole:
            if index.column() == 0:
                return tag.tagClass
            elif index.column() == 1:
                return tag.value
        elif role == self.TagClassRole:
            return tag.tagClass
        elif role == self.TagRole:
            return tag
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role in (Qt.DisplayRole, Qt.EditRole):
            if section == 0:
                return tr('Class')
            elif section == 1:
                return tr('Value')
        return None

    def rowCount(self, index):
        return len(self.__tags) if not index.isValid() else 0

    def columnCount(self, index):
        return 2

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or not (0 <= index.row() < len(self.__tags)) or role != Qt.EditRole:
            return False

        tag = self.__tags[index.row()]
        if index.column() == 0:
            new_value = tag.value.convertTo(value.valueType)
            tag.tagClass = value
            tag.value = new_value
        elif index.column() == 1:
            tag.value = TagValue(value)
        self.dataChanged.emit(index, index)

    def addTag(self, tag):
        self.beginInsertRows(QModelIndex(), len(self.__tags), len(self.__tags))
        self.__tags.append(tag)
        self.endInsertRows()

    def removeTag(self, tag):
        index_of_tag = self.__tags.index(tag)
        if index_of_tag >= 0:
            self.beginRemoveRows(QModelIndex(), index_of_tag, index_of_tag)
            del self.__tags[index_of_tag]
            self.endRemoveRows()

    def removeTags(self, tags):
        #todo: optimize?
        for tag in tags:
            self.removeTag(tag)


class AddTagDialog(Dialog):
    def __init__(self, parent, lib):
        Dialog.__init__(self, parent, name='generic_add_tag_dialog')
        self.lib = lib

        self.setWindowTitle(tr('Add tag'))

        self.classNameCombo = QComboBox(self)
        self.classNameCombo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.classNameModel = TagClassesModel(self.lib)
        self.classNameCombo.setModel(self.classNameModel)

        self.addClassButton = QToolButton(self)
        self.addClassButton.setText(tr('New class'))
        self.addClassButton.clicked.connect(self.__addClass)

        self.lblValueType = QLabel(self)

        self.valueEdit = ValueEditWidget(self, self.lib)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        self.classNameCombo.currentIndexChanged[str].connect(self.__onCurrentClassChanged)
        self.__onCurrentClassChanged(self.classNameCombo.currentText())

        classLayout = QHBoxLayout()
        classLayout.addWidget(self.classNameCombo)
        classLayout.addWidget(self.addClassButton)

        formLayout = QFormLayout()
        formLayout.addRow(tr('Class name'), classLayout)
        formLayout.addRow('', self.lblValueType)
        formLayout.addRow(tr('Value'), self.valueEdit)

        layout = QVBoxLayout(self)
        layout.addLayout(formLayout)
        layout.addWidget(self.buttonBox)

        setWidgetTabOrder(self, (self.valueEdit, self.classNameCombo, self.addClassButton, self.buttonBox))
        self.valueEdit.setFocus(Qt.OtherFocusReason)

    @property
    def tagClass(self):
        return self.lib.tagClass(self.classNameCombo.currentText())

    @tagClass.setter
    def tagClass(self, new_class):
        self.classNameCombo.setCurrentIndex(self.classNameCombo.findText(new_class.name))

    @property
    def tagValue(self):
        return TagValue(self.valueEdit.value)

    @tagValue.setter
    def tagValue(self, new_value):
        self.valueEdit.value = new_value

    def __onCurrentClassChanged(self, class_name):
        self.valueEdit.setEnabled(bool(class_name))

        value_type = TagValue.TYPE_NONE
        if class_name:
            tag_class = self.lib.tagClass(class_name)
            if tag_class:
                value_type = tag_class.valueType
        self.valueEdit.valueType = value_type

        self.lblValueType.setText(tr('(of type {0})').format(TagValue.typeString(value_type)))

    def __addClass(self):
        CreateClassDialog(self, self.lib).exec_()

    def accept(self):
        if not self.lib.tagClass(self.classNameCombo.currentText()):
            QMessageBox.information(self, tr('Error'), tr('No tag class {0} in current library!' \
                            .format(self.classNameCombo.text())))
        else:
            QDialog.accept(self)


_value_types_data = {
    TagValue.TYPE_NONE: (tr('None')),
    TagValue.TYPE_LOCATOR: (tr('Locator')),
    TagValue.TYPE_NODE_REFERENCE: (tr('Node reference')),
    TagValue.TYPE_NUMBER: (tr('Number')),
    TagValue.TYPE_TEXT: (tr('Text')),
}


class CreateClassDialog(Dialog):
    def __init__(self, parent, lib):
        Dialog.__init__(self, parent, name='generic_new_class_dialog')
        self.lib = lib

        self.setWindowTitle(tr('New class'))

        self.txtName = QLineEdit(self)  #todo: validator
        self.txtName.setValidator(ClassNameValidator())
        self.cmbType = QComboBox(self)
        self.cmbType.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        # fill with available types
        global _value_types_data
        for type_index in _value_types_data:
            self.cmbType.addItem(_value_types_data[type_index], type_index)
        # set TYPE_TEXT to be default type
        self.cmbType.setCurrentIndex(self.cmbType.findData(TagValue.TYPE_TEXT))
        self.chkHidden = QCheckBox(self)

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel, Qt.Horizontal, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

        formLayout = QFormLayout()
        formLayout.addRow(tr('Name'), self.txtName)
        formLayout.addRow(tr('Value type'), self.cmbType)
        formLayout.addRow(tr('Hidden'), self.chkHidden)

        layout = QVBoxLayout(self)
        layout.addLayout(formLayout)
        layout.addWidget(self.buttonBox)

    def accept(self):
        # create this class
        try:
            value_type = self.cmbType.itemData(self.cmbType.currentIndex(), Qt.UserRole)
            self.__createdClass = self.lib.createTagClass(self.txtName.text(), value_type, self.chkHidden.isChecked())
        except Exception as err:
            QMessageBox.warning(self, tr('Error while creating class'), tr('Failed to create class: {0}').format(err))
        else:
            QDialog.accept(self)


class ClassNameValidator(QValidator):
    def __init__(self):
        QValidator.__init__(self)

    def validate(self, input, pos):
        from organica.lib.objects import isCorrectIdent

        return (self.Acceptable, input, pos) if isCorrectIdent(input) else (self.Invalid, input, pos)
