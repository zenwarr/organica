import copy
from PyQt4.QtCore import QObject, pyqtSignal, Qt
from organica.utils.lockable import Lockable
import organica.utils.constants as constants


class _Set(QObject, Lockable):
    """Base class for all TagSet and NodeSet. Set allows watching library objects state
    and appearing and disappearing new objects.
    Set holds not Tag or Node objects, but its identities. You should manually
    query library for actual Tag or Node object.
    """

    elementAppeared = pyqtSignal(object)
    elementDisappeared = pyqtSignal(object)
    elementUpdated = pyqtSignal(object)
    resetted = pyqtSignal()

    def __init__(self, lib=None, query=None):
        QObject.__init__(self)
        Lockable.__init__(self)
        self.results = []
        self.__isFetched = False
        self.__lib = lib
        self.__query = None
        self.query = query

        if self.__lib is not None:
            self.__lib.resetted.connect(self.__reset)

    @property
    def isFetched(self):
        """Set is fetched if results are queried from database. Results are
        fetched only when needed."""
        with self.lock:
            return self.__isFetched

    @property
    def lib(self):
        """Library this Set is associated with"""
        with self.lock:
            return self.__lib

    @property
    def query(self):
        """Query this Set using to fetch results"""
        with self.lock:
            return self.__query

    @query.setter
    def query(self, new_query):
        with self.lock:
            if self.__query is not new_query:
                self.__query = new_query
                self.__reset()

    def ensureFetched(self):
        """Ensures that results are fetched from database."""
        with self.lock:
            if not self.__isFetched:
                self._fetch()
                self.__isFetched = True

    def _fetch(self):
        """Subclass should reimplement this method"""
        raise NotImplementedError()

    def __len__(self):
        with self.lock:
            self.ensureFetched()
            return len(self.results)

    def __getitem__(self, key):
        with self.lock:
            self.ensureFetched()
            return self.results[key]

    def __contains__(self, value):
        with self.lock:
            self.ensureFetched()
            return value in self.results

    def __iter__(self):
        with self.lock:
            self.ensureFetched()
            for result in self.results:
                yield result

    def __reset(self):
        with self.lock:
            self._results = []
            self.__isFetched = False
            self.resetted.emit()


class TagSet(_Set):
    def __init__(self, lib=None, query=None):
        _Set.__init__(self, lib, query)

        conn_type = Qt.DirectConnection if constants.disable_set_queued_connections else Qt.QueuedConnection
        if self.lib is not None:
            self.lib.tagCreated.connect(self.__onTagCreated, conn_type)
            self.lib.tagRemoved.connect(self.__onTagRemoved, conn_type)
            self.lib.tagUpdated.connect(self.__onTagUpdated, conn_type)
            self.lib.linkCreated.connect(self.__onLinkCreated, conn_type)
            self.lib.linkRemoved.connect(self.__onLinkRemoved, conn_type)

    @property
    def allTags(self):
        with self.lock:
            self.ensureFetched()
            return self.results

    def _fetch(self):
        with self.lock:
            if self.lib is not None:
                from organica.lib.filters import TagQuery

                normalized_query = self.query or TagQuery()
                self.results = [x.identity for x in self.lib.tags(normalized_query)]

    def __onTagCreated(self, new_tag):
        # when tag is created it can appear in set
        with self.lock:
            if self.isFetched:
                if self.query is None or self.query.passes(new_tag):
                    self.results.append(new_tag.identity)
                    self.elementAppeared.emit(new_tag.identity)

    def __onTagRemoved(self, removed_tag):
        with self.lock:
            if removed_tag.identity in self.results:
                self.results = [x for x in self.results if x != removed_tag.identity]
                self.elementDisappeared.emit(removed_tag.identity)

    def __onTagUpdated(self, updated_tag):
        with self.lock:
            if updated_tag.identity in self.results:
                if not (self.query is None or self.query.passes(updated_tag)):
                    self.results = [x for x in self.results if x != updated_tag.identity]
                    self.elementDisappeared.emit(updated_tag.identity)
                else:
                    self.elementUpdated.emit(updated_tag.identity)
            else:
                if self.query is None or self.query.passes(updated_tag):
                    self.results.append(updated_tag.identity)
                    self.elementAppeared.emit(updated_tag.identity)

    def __onLink(self, node, tag):
        self.__onTagUpdated(tag)

    def __onLinkCreated(self, node, tag):
        self.__onLink(node, tag)

    def __onLinkRemoved(self, node, tag):
        self.__onLink(node, tag)


class NodeSet(_Set):
    def __init__(self, lib=None, query=None):
        _Set.__init__(self, lib, query)

        if self.lib is not None:
            conn_type = Qt.DirectConnection if constants.disable_set_queued_connections else Qt.QueuedConnection
            self.lib.nodeUpdated.connect(self.__onNodeUpdated, conn_type)
            self.lib.nodeCreated.connect(self.__onNodeCreated, conn_type)
            self.lib.nodeRemoved.connect(self.__onNodeRemoved, conn_type)
            self.lib.linkCreated.connect(self.__onLinkCreated, conn_type)
            self.lib.linkRemoved.connect(self.__onLinkRemoved, conn_type)
            self.lib.tagUpdated.connect(self.__onTagUpdated, conn_type)

    @property
    def allNodes(self):
        with self.lock:
            self.ensureFetched()
            return self.results

    def _fetch(self):
        with self.lock:
            if self.lib is not None:
                from organica.lib.filters import NodeQuery

                normalized_query = self.query or NodeQuery()
                self.results = [x.identity for x in self.lib.nodes(normalized_query)]

    def __onNodeUpdated(self, updated_node):
        with self.lock:
            if updated_node.identity in self.results:
                if not (self.query is None or self.query.passes(updated_node)):
                    self.results = [n for n in self.results if n != updated_node.identity]
                    self.elementAppeared.emit(updated_node.identity)
                else:
                    self.elementUpdated.emit(updated_node.identity)
            elif self.query is None or self.query.passes(updated_node):
                self.results.append(updated_node.identity)
                self.elementAppeared.emit(updated_node.identity)

    def __onNodeCreated(self, created_node):
        with self.lock:
            if self.query is None or self.query.passes(created_node):
                self.results.append(created_node.identity)
                self.elementAppeared.emit(created_node.identity)

    def __onNodeRemoved(self, removed_node):
        with self.lock:
            if removed_node.identity in self.results:
                self.results = [n for n in self.results if n != removed_node.identity]
                self.elementDisappeared.emit(removed_node.identity)

    def __onLinkCreated(self, node, tag):
        self.__onLink(node, tag)

    def __onLinkRemoved(self, node, tag):
        self.__onLink(node, tag)

    def __onLink(self, node, tag):
        self.__onNodeUpdated(node)

    def __onTagUpdated(self, updated_tag):
        with self.lock:
            # get nodes this tag linked with
            from organica.lib.filters import NodeQuery
            for node in self.lib.nodes(NodeQuery(linked_with=updated_tag)):
                self.__onNodeUpdated(node)
