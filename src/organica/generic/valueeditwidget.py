from PyQt4.QtCore import Qt, pyqtSignal
from PyQt4.QtGui import QWidget, QVBoxLayout, QSpinBox, QLineEdit, QComboBox
from organica.lib.objects import TagValue
from organica.lib.objectsmodel import ObjectsModel
from organica.gui.patheditwidget import PathEditWidget
from organica.lib.locator import Locator


class ValueEditWidget(QWidget):
    """Allows editing of TagValue, providing different editors for each value type.
    """

    valueChanged = pyqtSignal(TagValue)

    def __init__(self, parent, lib):
        QWidget.__init__(self, parent)
        self.lib = lib

        self.wlayout = QVBoxLayout(self)
        self.wlayout.setContentsMargins(0, 0, 0, 0)

        self.__valueType = TagValue.TYPE_NONE
        self.__editWidget = None

    @property
    def value(self):
        return self.__editWidget.value if self.__editWidget is not None else TagValue()

    @value.setter
    def value(self, new_value):
        if not hasattr(self, '_types_data'):
            self._types_data = {
                TagValue.TYPE_NONE: NoneEditor,
                TagValue.TYPE_NUMBER: NumberEditor,
                TagValue.TYPE_NODE_REFERENCE: NodeReferenceEditor,
                TagValue.TYPE_LOCATOR: UrlEditor,
                TagValue.TYPE_TEXT: TextEditor
            }

        new_value = TagValue(new_value)
        if new_value.valueType == self.__valueType:
            self.__editWidget.value = new_value
        else:
            # delete old widget
            if self.__editWidget is not None:
                self.__editWidget.tagValueChanged.disconnect(self.valueChanged)
                self.wlayout.removeWidget(self.__editWidget)
                self.__editWidget.deleteLater()

            # find widget class for this value type
            widget_class = self._types_data[new_value.valueType] if new_value.valueType in self._types_data else None
            if widget_class is not None:
                self.__editWidget = widget_class(self, self.lib)
                self.__editWidget.tagValueChanged.connect(self.valueChanged)
                self.wlayout.addWidget(self.__editWidget)
                self.__valueType = new_value.valueType
                self.__editWidget.value = new_value

    @property
    def valueType(self):
        return self.__valueType

    @valueType.setter
    def valueType(self, new_value_type):
        if self.__valueType != new_value_type:
            self.value = self.value.convertTo(new_value_type)


class NoneEditor(QWidget):
    tagValueChanged = pyqtSignal(TagValue)

    def __init__(self, parent, lib):
        QWidget.__init__(self, parent)

    @property
    def value(self):
        return TagValue()

    @value.setter
    def value(self, new_value):
        pass


class NumberEditor(QSpinBox):
    tagValueChanged = pyqtSignal(TagValue)

    def __init__(self, parent, lib):
        QSpinBox.__init__(self, parent)
        self.valueChanged[int].connect(lambda x: self.tagValueChanged.emit(TagValue(x)))

    @property
    def value(self):
        return TagValue(QSpinBox.value(self), TagValue.TYPE_NUMBER)

    @value.setter
    def value(self, new_value):
        QSpinBox.setValue(self, new_value.number or 0)


class NodeReferenceEditor(QComboBox):
    tagValueChanged = pyqtSignal(TagValue)

    def __init__(self, parent, lib):
        class CustomColumn(object):
            title = ''

            def data(self, index, node, role):
                if role == Qt.DisplayRole:
                    return '#{0} - {1}'.format(node.id, node.displayName)
                return None

        QComboBox.__init__(self, parent)
        self.lib = lib

        self.currentIndexChanged[str].connect(lambda x: self.tagValueChanged.emit(TagValue(x)))

        model = ObjectsModel(self.lib)
        model.columns = [CustomColumn()]
        self.setModel(model)
        self.setModelColumn(0)

    @property
    def value(self):
        return TagValue(self.itemData(self.currentIndex(), ObjectsModel.NodeIdentityRole), TagValue.TYPE_NODE_REFERENCE)

    @value.setter
    def value(self, new_value):
        referred_identity = new_value.nodeReference
        node_index = self.findData(referred_identity, ObjectsModel.NodeIdentityRole)
        if node_index > 0:
            self.setCurrentIndex(node_index)


class UrlEditor(PathEditWidget):
    tagValueChanged = pyqtSignal(TagValue)

    def __init__(self, parent, lib):
        PathEditWidget.__init__(self, parent)
        self.pathChanged.connect(lambda x: self.tagValueChanged.emit(TagValue(Locator(x))))

    @property
    def value(self):
        return TagValue(Locator(self.path), TagValue.TYPE_LOCATOR)

    @value.setter
    def value(self, new_value):
        self.path = new_value.locator.url.toString()


class TextEditor(QLineEdit):
    tagValueChanged = pyqtSignal(TagValue)

    def __init__(self, parent, lib):
        QLineEdit.__init__(self, parent)
        self.textChanged.connect(lambda x: self.tagValueChanged.emit(TagValue(x)))

    @property
    def value(self):
        return TagValue(self.text(), TagValue.TYPE_TEXT)

    @value.setter
    def value(self, new_value):
        self.setText(new_value.text)
