from PyQt4.QtCore import Qt, pyqtSignal, QUrl
from PyQt4.QtGui import QWidget, QVBoxLayout, QSpinBox, QLineEdit, QComboBox, QCheckBox
from organica.lib.objects import TagValue
from organica.lib.objectsmodel import ObjectsModel
from organica.gui.patheditwidget import PathEditWidget
from organica.lib.locator import Locator
from organica.utils.helpers import tr


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
                self.__editWidget.hide()
                self.__editWidget.deleteLater()

            self.__editWidget = None

            # find widget class for this value type
            widget_class = self._types_data[new_value.valueType] if new_value.valueType in self._types_data else None
            if widget_class is not None:
                self.__editWidget = widget_class(self, self.lib)
                self.__editWidget.tagValueChanged.connect(self.valueChanged)
                self.wlayout.addWidget(self.__editWidget)
                self.__valueType = new_value.valueType
                self.__editWidget.value = new_value
                self.setFocusProxy(self.__editWidget)

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


class UrlEditor(QWidget):
    tagValueChanged = pyqtSignal(TagValue)

    def __init__(self, parent, lib):
        QWidget.__init__(self, parent)
        self.lib = lib

        self.pathEditWidget = PathEditWidget(self)
        self.pathEditWidget.pathChanged.connect(self.__onPathChanged)
        self.chkCopyToStorage = QCheckBox(tr('Copy to local storage'), self)
        self.chkCopyToStorage.setVisible(lib is not None and lib.storage is not None)

        self.m_layout = QVBoxLayout(self)
        self.m_layout.setContentsMargins(0, 0, 0, 0)
        self.m_layout.addWidget(self.pathEditWidget)
        self.m_layout.addWidget(self.chkCopyToStorage)

    @property
    def value(self):
        if self.chkCopyToStorage.isChecked():
            return TagValue(Locator.fromManagedFile('', self.lib, self.__pathToLocator(self.pathEditWidget.path).url))
        else:
            return TagValue(self.__pathToLocator(self.pathEditWidget.path))

    @value.setter
    def value(self, new_value):
        self.chkCopyToStorage.setChecked(bool(new_value.locator.isManagedFile and new_value.locator.sourceUrl))
        self.pathEditWidget.path = self.__locatorToPath(new_value.locator)

    def __onPathChanged(self, new_path):
        locator = self.__pathToLocator(new_path)
        self.chkCopyToStorage.setEnabled(locator.isLocalFile and not locator.isManagedFile)
        self.tagValueChanged.emit(TagValue(locator))

    def __pathToLocator(self, path):
        """Converts value from PathEditWidget (which can be not local file path, but an url) to Locator"""
        if not path:
            return Locator()
        elif QUrl(path).scheme() in ('file', ''):
            return Locator.fromLocalFile(path)
        else:
            return Locator.fromUrl(path, self.lib)

    def __locatorToPath(self, locator):
        """Converts Locator to string suitable for PathEditWidget"""
        return locator.localFilePath if locator.isLocalFile else locator.url.toString()


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
