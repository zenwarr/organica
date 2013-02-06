from PyQt4.QtCore import Qt
from PyQt4.QtGui import QStandardItemModel, QStandardItem


class TagClassesModel(QStandardItemModel):
    TagClassIdentityRole = Qt.UserRole + 200

    def __init__(self, parent=None):
        QStandardItemModel.__init__(self, parent)
        self.__showHidden = False
        self.__showSpecialClass = False
        self.__specialClassName = ''
        self.__lib = None

    @property
    def lib(self):
        return self.__lib

    @lib.setter
    def lib(self, new_lib):
        if self.__lib is not new_lib:
            self.__lib = new_lib
            self.__fetch()

    def __fetch(self):
        self.clear()
        if self.__lib:
            if self.__showSpecialClass and self.__specialClassName:
                special_item = QStandardItem()
                special_item.setText(self.__specialClassName)
                special_item.setForeground(Qt.gray)
                self.appendRow(special_item)

            for tag_class in self.__lib.tagClasses():
                if self.__showHidden or not tag_class.hidden:
                    self.appendRow(self.__createItemForClass(tag_class))

    def __createItemForClass(self, tag_class):
        item = QStandardItem()
        item.setText(tag_class.name)
        if tag_class.hidden:
            item.setForeground(Qt.gray)
        item.setData(tag_class.identity, self.TagClassIdentityRole)
        return item

    @property
    def showHidden(self):
        return self.__showHidden

    @showHidden.setter
    def showHidden(self, new_show_hidden):
        if self.__showHidden != new_show_hidden:
            self.__showHidden = new_show_hidden
            self.__fetch()

    @property
    def showSpecialClass(self):
        return self.__showSpecialClass

    @showSpecialClass.setter
    def showSpecialClass(self, new_show):
        if new_show != self.__showSpecialClass:
            self.__showSpecialClass = new_show
            self.__fetch()

    @property
    def specialClassName(self):
        return self.__specialClassName

    @specialClassName.setter
    def specialClassName(self, new_class):
        if self.__specialClassName != new_class:
            self.__specialClassName = new_class
            self.__fetch()
