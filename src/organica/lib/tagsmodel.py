import copy

from PyQt4.QtCore import Qt, QAbstractItemModel, QModelIndex

from organica.lib.sets import TagSet
from organica.utils.lockable import Lockable
from organica.lib.filters import TagQuery


class _Leaf(object):
    def __init__(self):
        self.id = -1  # unique leaf id
        self.children = []  # list of ids
        self.tagset = None
        self.parentId = -1
        self.level = 0
        self.tag = None
        self.cachedClassName = ''
        self.cachedValue = ''


class TagsModel(QAbstractItemModel, Lockable):
    """Model represents library tag structure in hierarchical form.
    This will not work correctly with queries using 'unused' conditions.
    """

    TagIdentityRole = Qt.UserRole + 200

    def __init__(self, lib):
        QAbstractItemModel.__init__(self)
        Lockable.__init__(self)
        self.__lib = lib
        self.__hierarchy = []  # list of strings (class names)
        self.__leaves = dict()  # dictionary of leaves by id
        self.__showHidden = False  # True if model should take hidden tags into account
        self.__lastNodeId = -1
        self.__filters = []
        self.__reset()

    @property
    def lib(self):
        with self.lock:
            return self.__lib

    @property
    def hierarchy(self):
        with self.lock:
            return copy.deepcopy(self.__hierarchy)

    @hierarchy.setter
    def hierarchy(self, new_hierarchy):
        with self.lock:
            if self.__hierarchy != new_hierarchy:
                self.__hierarchy = new_hierarchy
                self.__reset()

    @property
    def showHidden(self):
        with self.lock:
            return self.__showHidden

    @showHidden.setter
    def showHidden(self, new_show_hidden):
        with self.lock:
            if self.__showHidden != new_show_hidden:
                self.__showHidden = new_show_hidden
                self.__reset()

    @property
    def query(self):
        """Query used to fetch first-level items. Should be of TagQuery type.
        """

        with self.lock:
            r_filter = self.__filters[0] if self.__filters else TagQuery()
            for f in self.__filters[1:]:
                r_filter = r_filter & f
            return r_filter

    @property
    def filters(self):
        with self.lock:
            return copy.deepcopy(self.__filters)

    @filters.setter
    def filters(self, new_filters):
        with self.lock:
            self.__filters = new_filters
            self.__reset()

    def __reset(self):
        self.__leaves = dict()
        self.__leaves[-1] = _Leaf()  # root leaf
        self.__lastNodeId = -1
        if self.lib is not None:
            self.__fetch(-1)

    def __fetch(self, leaf):
        if isinstance(leaf, int):
            leaf = self.__leaves[leaf]

        self.beginResetModel()

        # clear list of children and remove them from
        if leaf.children:
            self.__leaves = [x for x in self.__leaves if x not in leaf.children]
            leaf.children = []

        # disconnect any TagSet signals bound to this object
        if leaf.tagset is not None:
            leaf.tagset.elementAppeared.disconnect(self.__onElementAppeared)
            leaf.tagset.elementDisappeared.disconnect(self.__onElementDisappeared)
            leaf.tagset.elementUpdated.disconnect(self.__onElementUpdated)
            leaf.tagset.resetted.disconnect(self.__onTagsetResetted)

        # do not fetch anything for leaves on last level
        if leaf.level >= len(self.__hierarchy):
            self.endResetModel()
            return

        # build filter for children of this leaf
        if self.__hierarchy[leaf.level] == '*':
            children_filter = TagQuery()
        else:
            children_filter = TagQuery(tag_class=self.__hierarchy[leaf.level])
        if leaf.level > 0:
            children_filter = children_filter & TagQuery(friend_of=leaf.tag)
        if not self.__showHidden:
            children_filter = children_filter & TagQuery(hidden=False)
        if leaf.level == 0:
            children_filter = children_filter & self.query

        leaf.tagset = TagSet(self.lib, children_filter)

        # recursively fetch all children
        with leaf.tagset.lock:
            for tag_identity in leaf.tagset.allTags:
                self.__doInsertLeaf(leaf, tag_identity)

            # and connect to signals of TagSet
            leaf.tagset.elementAppeared.connect(self.__onElementAppeared)
            leaf.tagset.elementDisappeared.connect(self.__onElementDisappeared)
            leaf.tagset.elementUpdated.connect(self.__onElementUpdated)
            leaf.tagset.resetted.connect(self.__onTagsetResetted)

        self.endResetModel()

    def __doInsertLeaf(self, parent_leaf, tag_identity):
        child_leaf = _Leaf()
        child_leaf.id = self.__lastNodeId + 1
        self.__lastNodeId += 1
        child_leaf.level = parent_leaf.level + 1
        child_leaf.tag = tag_identity

        actual_tag = self.lib.tag(tag_identity)
        child_leaf.cachedClassName = actual_tag.className
        child_leaf.cachedValue = actual_tag.value

        child_leaf.parentId = parent_leaf.id
        parent_leaf.children.append(child_leaf.id)
        self.__leaves[child_leaf.id] = child_leaf
        if child_leaf.level < len(self.__hierarchy):
            self.__fetch(child_leaf)

    def __processLeaf(self, tag, routine):
        target_tagset = self.sender()
        assert target_tagset is not None

        for leaf in self.__leaves.values():
            if leaf.tagset is target_tagset:
                routine(leaf, tag)
                break

    def __insertLeaf(self, leaf, tag):
        new_leaf_index = len(leaf.children)
        self.beginInsertRows(self.__indexForLeaf(leaf), new_leaf_index, new_leaf_index)
        self.__doInsertLeaf(leaf, tag)
        self.endInsertRows()

    def __onElementAppeared(self, element):
        with self.lock:
            self.__processLeaf(element, self.__insertLeaf)

    def __removeLeaf(self, leaf, tag):
        child_id = self.__childIdForTag(leaf, tag)
        if child_id is not None:
            child_row = leaf.children.index(child_id)
            self.beginRemoveRows(self.__indexForLeaf(leaf), child_row, child_row)
            leaf.children = [x for x in leaf.children if x != child_id]
            self.endRemoveRows()

    def __childIdForTag(self, leaf, tag):
        for child_id in leaf.children:
            if self.__leaves[child_id].tag == tag:
                return child_id
        else:
            return None

    def __onElementDisappeared(self, element):
        with self.lock:
            self.__processLeaf(element, self.__removeLeaf)

    def __updateLeaf(self, leaf, tag):
        child_id = self.__childIdForTag(leaf, tag)
        if child_id is not None:
            self.dataChanged.emit(self.__indexForLeaf(child_id),
                                  self.__indexForLeaf(child_id, self.columnCount() - 1))

    def __onElementUpdated(self, element):
        with self.lock:
            self.__processLeaf(element, self.__updateLeaf)

    def __onTagsetResetted(self):
        with self.lock:
            self.__reset()

    def __indexForLeaf(self, leaf, column=0):
        if isinstance(leaf, int):
            leaf = self.__leaves[leaf]

        if leaf.id == -1:
            return QModelIndex()
        parent_leaf = self.__leaves[leaf.parentId]
        assert leaf.id in parent_leaf.children
        return self.createIndex(parent_leaf.children.index(leaf.id), column, leaf.id)

    def __leafForIndex(self, index):
        if not index.isValid():
            return self.__leaves[-1]
        return self.__leaves[index.internalId()]

    def flags(self, index):
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable

    def data(self, index, role=Qt.DisplayRole):
        with self.lock:
            if not index.isValid():
                return None

            leaf = self.__leafForIndex(index)
            if leaf is None:
                return None

            if role == Qt.DisplayRole or role == Qt.EditRole:
                if index.column() == 0:
                    return leaf.cachedClassName
                elif index.column() == 1:
                    return str(leaf.cachedValue)
            elif role == TagsModel.TagIdentityRole:
                return leaf.tag
            return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section == 0:
                return 'Name'
            elif section == 1:
                return 'Value'

    def rowCount(self, index=QModelIndex()):
        with self.lock:
            leaf = self.__leafForIndex(index)
            return len(leaf.children) if leaf is not None else 0

    def columnCount(self, index=QModelIndex()):
        return 2

    def index(self, row, column, parent=QModelIndex()):
        with self.lock:
            if row < 0 or not (0 <= column < 2):
                return QModelIndex()

            parent_leaf = self.__leafForIndex(parent)
            if parent_leaf is None:
                return QModelIndex()

            if row >= len(parent_leaf.children):
                return QModelIndex()
            return self.createIndex(row, column, parent_leaf.children[row])

    def parent(self, index):
        with self.lock:
            if not index.isValid():
                return QModelIndex()

            leaf = self.__leafForIndex(index)
            if leaf is None or leaf.parentId == -1:
                return QModelIndex()

            return self.__indexForLeaf(leaf.parentId)

    def indexesForTag(self, tag_identity, column=0):
        """Get list of indexes that refer to given tag.
        """

        with self.lock:
            actual_tag = self.lib.tag(tag_identity)
            if actual_tag is not None and '*' not in self.__hierarchy and actual_tag.className not in self.__hierarchy:
                return []

            return [self.__indexForLeaf(x) for x in self.__leaves.values() if x.tag == tag_identity]
