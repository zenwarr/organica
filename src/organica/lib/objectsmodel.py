import os
from PyQt4.QtCore import Qt, QAbstractItemModel, QModelIndex
from organica.utils.helpers import removeLastSlash, tr
from organica.utils.lockable import Lockable
from organica.lib.sets import NodeSet


class NodeNameColumn(object):
    def data(self, index, node, role=Qt.DisplayRole):
        return node.displayName if role == Qt.DisplayRole else None

    title = tr('Name')


class NodeLocatorColumn(object):
    def data(self, index, node, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            from organica.lib.filters import TagQuery

            locators = [tag.value.locator for tag in node.tags(TagQuery(tag_class='locator'))]
            if not locators:
                return None
            else:
                choosen_locator = locators[0]

            if choosen_locator.isLocalFile:
                filename = removeLastSlash(choosen_locator.localFilePath)
                return os.path.basename(filename)
            else:
                return str(locator)
        return None

    title = tr('Locator')


def FormattedColumn(object):
    def __init__(self, template, title=tr('Custom')):
        self.__template = template
        self.title = title

    def data(self, index, node, role=Qt.DisplayRole):
        from organica.lib.formatstring import FormatString

        if role == Qt.DisplayRole:
            return FormatString(self.__template).format(node)
        return None


class ObjectsModel(QAbstractItemModel, Lockable):
    NodeIdentityRole = Qt.UserRole + 200

    def __init__(self, lib):
        QAbstractItemModel.__init__(self)
        Lockable.__init__(self)
        self.__lib = lib
        self.__set = NodeSet(self.__lib)
        self.__columns = [NodeNameColumn(), NodeLocatorColumn()]
        self.__cached_nodes = []

        with self.__set.lock:
            self.__cached_nodes = self.__set.allNodes

            self.__set.elementAppeared.connect(self.__onElementAppeared)
            self.__set.elementDisappeared.connect(self.__onElementDisappeared)
            self.__set.elementUpdated.connect(self.__onElementUpdated)
            self.__set.resetted.connect(self.__onResetted)

    @property
    def lib(self):
        with self.lock:
            return self.__lib

    @property
    def query(self):
        with self.lock:
            return self.__set.query

    @query.setter
    def query(self, new_query):
        with self.lock:
            self.__set.query = new_query

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and 0 <= index.row() < len(self.__cached_nodes) and 0 <= index.column() < len(self.__columns):
            node = self.lib.node(self.__cached_nodes[index.row()])
            if node is not None:
                if role == self.NodeIdentityRole:
                    return node.identity
                else:
                    column_object = self.__columns[index.column()]
                    return column_object.data(index, node, role)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        with self.lock:
            if orientation == Qt.Horizontal:
                if role == Qt.DisplayRole:
                    if 0 <= section < len(self.__columns):
                        return self.__columns[section].title
            else:
                if 0 <= section < len(self.__cached_nodes):
                    return str(section)
        return None

    def rowCount(self, index=QModelIndex()):
        with self.lock:
            return len(self.__cached_nodes)

    def columnCount(self, index=QModelIndex()):
        with self.lock:
            return len(self.__columns)

    def index(self, row, column, parent=QModelIndex()):
        with self.lock:
            if 0 <= row < len(self.__cached_nodes) and 0 <= column < len(self.__columns) and not parent.isValid():
                return self.createIndex(row, column)
        return QModelIndex()

    def parent(self, index):
        return QModelIndex()

    @property
    def columns(self):
        with self.lock:
            return self.__columns

    @columns.setter
    def columns(self, new_columns):
        with self.lock:
            if new_columns != self.__columns:
                self.__columns = new_columns
                self.reset()

    def __onElementAppeared(self, new_element):
        with self.lock:
            # append new element to end of list
            node_to_cache = self.lib.node(new_element)
            if node_to_cache is not None:
                self.beginInsertRows(QModelIndex(), len(self.__cached_nodes), len(self.__cached_nodes))
                self.__cached_nodes.append(node_to_cache.identity)
                self.endInsertRows()

    def __onElementDisappeared(self, removed_element):
        with self.lock:
            for node_index in range(len(self.__cached_nodes)):
                if self.__cached_nodes[node_index] == removed_element:
                    self.beginRemoveRows(QModelIndex(), node_index, node_index)
                    del self.__cached_nodes[node_index]
                    self.endRemoveRows()

    def __onElementUpdated(self, updated_element):
        with self.lock:
            for node_index in range(len(self.__cached_nodes)):
                if self.__cached_nodes[node_index] == updated_element:
                    self.dataChanged.emit(self.index(node_index, 0), self.index(node_index,
                                                                                self.columnCount() - 1))

    def __onResetted(self):
        with self.lock:
            self.beginResetModel()
            self.__cached_nodes = []
            self.__fetch()
            self.endResetModel()

    def __fetch(self):
        with self.lock:
            self.__cached_nodes = [self.lib.node(identity) for identity in self.__set]
