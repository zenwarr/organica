from copy import copy

from PyQt4.QtCore import QObject, pyqtSignal, Qt

from organica.utils.lockable import Lockable
import organica.utils.constants as constants


class _Set(QObject, Lockable):
    """Base class for all TagSet and NodeSet. Set allows watching library objects state
    and appearing and disappearing new objects.
    Monitoring Set elements can be paused to save system resources. When isPaused is
    True, no signals will be emitted by Set object. Library state will be still monitored
    and isDirty boolean flag will be set after first change. Once isPaused becomes False,
    Set reloads elements by querying database if isDirty is True.

    Set holds not Tag or Node objects, but its identities. You should manually
    query library for actual Tag or Node object.
    """

    elementAppeared = pyqtSignal(object)
    elementDisappeared = pyqtSignal(object)
    elementUpdated = pyqtSignal(object)
    resetted = pyqtSignal()

    def __init__(self, lib, query):
        QObject.__init__(self)
        Lockable.__init__(self)
        self._query = query
        self._results = []
        self.__isFetched = False
        self.__lib = lib
        self.__isPaused = False
        self.isDirty = False
        self.lib.resetted.connect(self.onResetted)

    @property
    def isFetched(self):
        """Set is fetched if results are queried from database. Results are
        fetched only when needed.
        """

        with self.lock:
            return self.__isFetched

    @property
    def lib(self):
        """Library this Set is assotiated with"""

        with self.lock:
            return self.__lib

    @property
    def query(self):
        """Query this Set using to fetch results"""

        with self.lock:
            return self._query

    @property
    def isPaused(self):
        """When Set is paused, no signals are emitted on changes, but results
        are resetted if needed when isPaused becomes True.
        """

        with self.lock:
            return self.__isPaused

    @isPaused.setter
    def isPaused(self, value):
        with self.lock:
            if value != self.__isPaused:
                if value:
                    self.isDirty = False
                    self.__isPaused = True
                else:
                    if self.isDirty:
                        self._fetch()
                        self.resetted.emit()
                    self.isDirty = False
                    self.__isPaused = False

    def onResetted(self):
        with self.lock:
            if self.needUpdate:
                self._results.clear()
                self.resetted.emit()
            elif not self.isDirty:
                self.isDirty = True

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
            return len(self._results)

    def __getitem__(self, key):
        with self.lock:
            self.ensureFetched()
            return self._results[key]

    def __contains__(self, value):
        with self.lock:
            self.ensureFetched()
            return value in self._results

    @property
    def needUpdate(self):
        """Check if Set should update result list.
        """

        with self.lock:
            return self.isFetched and not self.isPaused


class TagSet(_Set):
    def __init__(self, lib, query):
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
            return copy(self._results)

    def _fetch(self):
        with self.lock:
            if self.lib is not None:
                self._results = [x.identity for x in self.lib.tags(self._query)]

    def __onTagCreated(self, new_tag):
        # when tag is created it can appear in set
        with self.lock:
            if self.needUpdate:
                if self.query.passes(new_tag):
                    self._results.append(new_tag.identity)
                    self.elementAppeared.emit(new_tag.identity)
            elif not self.isDirty:
                if self.query.passes(new_tag):
                    self.isDirty = True

    def __onTagRemoved(self, removed_tag):
        with self.lock:
            if self.needUpdate:
                if removed_tag.identity in self._results:
                    self._results = [x for x in self._results if x != removed_tag.identity]
                    self.elementDisappeared.emit(removed_tag.identity)
            elif not self.isDirty:
                if removed_tag.identity in self._results:
                    self.isDirty = True

    def __onTagUpdated(self, updated_tag):
        with self.lock:
            if self.needUpdate:
                if updated_tag.identity in self._results:
                    if not self.query.passes(updated_tag):
                        self._results = [x for x in self._results if x != updated_tag.identity]
                        self.elementDisappeared.emit(updated_tag.identity)
                    else:
                        self.elementUpdated.emit(updated_tag.identity)
                else:
                    if self.query.passes(updated_tag):
                        self._results.append(updated_tag.identity)
                        self.elementAppeared.emit(updated_tag.identity)
            elif not self.isDirty:
                if updated_tag.identity in self._results or self.query.passes(updated_tag):
                    self.isDirty = True

    def __onLink(self, node, tag):
        self.__onTagUpdated(tag)

    def __onLinkCreated(self, node, tag):
        self.__onLink(node, tag)

    def __onLinkRemoved(self, node, tag):
        self.__onLink(node, tag)


class NodeSet(_Set):
    def __init__(self, lib, query):
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
            return copy(self._results)

    def _fetch(self):
        with self.lock:
            if self.lib is not None:
                self._results = [x.identity for x in self.lib.nodes(self._query)]

    def __onNodeUpdated(self, updated_node):
        with self.lock:
            if self.needUpdate:
                if updated_node.identity in self._results:
                    if not self.query.passes(updated_node):
                        self._results = [n for n in self._results if n != updated_node.identity]
                        self.elementAppeared.emit(updated_node.identity)
                    else:
                        self.elementUpdated.emit(updated_node.identity)
                elif self.query.passes(updated_node):
                    self._results.append(updated_node.identity)
                    self.elementAppeared.emit(updated_node.identity)
            elif not self.isDirty:
                if updated_node.identity in self._results or self.query.passes(updated_node):
                    self.isDirty = True

    def __onNodeCreated(self, created_node):
        with self.lock:
            if self.needUpdate:
                if self.query.passes(created_node):
                    self._results.append(created_node.identity)
                    self.elementAppeared.emit(created_node.identity)
            elif not self.isDirty:
                if self.query.passes(created_node):
                    self.isDirty = True

    def __onNodeRemoved(self, removed_node):
        with self.lock:
            if self.needUpdate:
                if removed_node.identity in self._results:
                    self._results = [n for n in self._results if n != removed_node.identity]
                    self.elementDisappeared.emit(removed_node.identity)
            elif not self.isDirty:
                if removed_node.identity in self._results:
                    self.isDirty = True

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
