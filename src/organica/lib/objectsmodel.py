from PyQt4.QtCore import Qt, QAbstractItemModel, QModelIndex
from organica.utils.helpers import removeLastSlash, tr
from organica.utils.lockable import Lockable
from organica.lib.sets import NodeSet
from organica.lib.filters import TagQuery
from organica.lib.objects import get_identity


class NodeNameColumn(object):
    def data(self, index, node, role=Qt.DisplayRole):
        return node.displayName if role == Qt.DisplayRole else None

    title = tr('Name')


class FormattedColumn(object):
    def __init__(self, template, title=tr('Custom')):
        from organica.lib.formatstring import FormatString

        self.__template = FormatString(template)
        self.title = title

    def data(self, index, node, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            return self.__template.format(node)
        return None


class NodeLocatorColumn(FormattedColumn):
    def __init__(self):
        FormattedColumn.__init__(self, '{locator: max=1, end="", locator=name}', tr('Locator'))



class ObjectsModel(QAbstractItemModel, Lockable):
    NodeIdentityRole = Qt.UserRole + 200

    def __init__(self, lib):
        QAbstractItemModel.__init__(self)
        Lockable.__init__(self)
        self.__lib = lib
        self.__set = NodeSet(self.__lib)
        self.__columns = [NodeNameColumn(), NodeLocatorColumn()]
        self.__cached_nodes = []
        self.__filters = []

        with self.__set.lock:
            self.__fetch()

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
            r_filter = self.__filters[0] if self.__filters else TagQuery()
            for f in self.__filters[1:]:
                r_filter = r_filter & f
            return r_filter

    @property
    def filters(self):
        with self.lock:
            return self.__filters

    @filters.setter
    def filters(self, new_filters):
        with self.lock:
            self.__filters = new_filters
            self.__set.query = self.query

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid() and self.hasIndex(index.row(), index.column()):
            node = self.__cached_nodes[index.row()]
            if node is not None:
                if role == self.NodeIdentityRole:
                    return node.identity
                else:
                    return self.__columns[index.column()].data(index, node, role)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        with self.lock:
            if orientation == Qt.Horizontal:
                if role == Qt.DisplayRole:
                    if 0 <= section < len(self.__columns):
                        return self.__columns[section].title
            elif 0 <= section < len(self.__cached_nodes):
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
            if not parent.isValid() and self.hasIndex(row, column):
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
                self.__cached_nodes.append(node_to_cache)
                self.endInsertRows()

    def __onElementDisappeared(self, removed_element):
        with self.lock:
            for node_index in range(len(self.__cached_nodes)):
                if self.__cached_nodes[node_index].identity == removed_element:
                    self.beginRemoveRows(QModelIndex(), node_index, node_index)
                    del self.__cached_nodes[node_index]
                    self.endRemoveRows()
                    break

    def __onElementUpdated(self, updated_element):
        with self.lock:
            for node_index in range(len(self.__cached_nodes)):
                if self.__cached_nodes[node_index].identity == updated_element:
                    self.dataChanged.emit(self.index(node_index, 0), self.index(node_index, self.columnCount() - 1))
                    break

    def __onResetted(self):
        with self.lock:
            self.beginResetModel()
            self.__cached_nodes = []
            self.__fetch()
            self.endResetModel()

    def __fetch(self):
        with self.lock:
            self.__cached_nodes = [ident.lib.node(ident) for ident in self.__set.allNodes]

    def indexOfNode(self, node):
        row = self.__cached_nodes.index(get_identity(node))
        return self.index(row, 0) if row >= 0 else QModelIndex()

