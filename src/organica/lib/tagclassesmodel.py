from PyQt4.QtCore import Qt
from PyQt4.QtGui import QStandardItemModel, QStandardItem
from organica.utils.helpers import uncase


class TagClassesModel(QStandardItemModel):
    TagClassIdentityRole = Qt.UserRole + 200

    def __init__(self, lib=None):
        QStandardItemModel.__init__(self)
        self.__showHidden = False
        self.__showSpecialClass = False
        self.__specialClassName = ''
        self.__lib = None
        self.lib = lib

    @property
    def lib(self):
        return self.__lib

    @lib.setter
    def lib(self, new_lib):
        if self.__lib is not new_lib:
            if self.__lib is not None:
                self.__lib.classCreated.disconnect(self.__onClassCreated)
                self.__lib.classRemoved.disconnect(self.__onClassRemoved)

            self.__lib = new_lib

            self.clear()

            if self.__lib is not None:
                with self.__lib.lock:
                    self.__fetch()
                    self.__lib.classCreated.connect(self.__onClassCreated)
                    self.__lib.classRemoved.connect(self.__onClassRemoved)

    def __fetch(self):
        self.clear()
        if self.__lib:
            for tag_class in self.__lib.tagClasses():
                if self.__showHidden or not tag_class.hidden:
                    self.appendRow(self.__createItemForClass(tag_class))

            self.sort(0)

            if self.__showSpecialClass and self.__specialClassName:
                special_item = QStandardItem()
                special_item.setText(self.__specialClassName)
                special_item.setForeground(Qt.gray)
                self.insertRow(0, special_item)

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

    def __onClassCreated(self, new_tag_class):
        if self.__showHidden or not new_tag_class.hidden:
            # find position to insert this item to keep list sorted
            row_index_for_class = 1 if self.__showSpecialClass else 0
            for row_index in range(row_index_for_class, self.rowCount()):
                if uncase(self.index(row_index, 0).data(Qt.DisplayRole)) <= uncase(new_tag_class.name):
                    row_index_for_class += 1
                else:
                    break
            self.insertRow(row_index_for_class, self.__createItemForClass(new_tag_class))

    def __onClassRemoved(self, removed_tag_class):
        for row_index in range(self.rowCount()):
            if self.index(row_index, 0).data(self.TagClassIdentityRole) == removed_tag_class.identity:
                self.removeRows(row_index, 1)
                break
