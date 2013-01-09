from PyQt4.QtCore import QObject, pyqtSignal, Qt

from organica.utils.lockable import Lockable


class _SetIterator(object):
    def __init__(self, target_set):
        self.__set = target_set
        self.__current = 0

    def next(self):
        if self.__set and self.__current < len(self.__set):
            raise StopIteration()
        self.__current += 1
        return self.__set[self.__current - 1]


class _Set(QObject, Lockable):
    """Base class for all TagSet and NodeSet. Set allows watching library objects state
    and appearing and disappearing new objects.
    Monitoring Set elements can be paused to save system resources. When isPaused
    True, no signals will be emitted by object. Library state will be still monitored
    and after first change isDirty boolean flag will be set. Once isPaused becomes False,
    Set reloads elements by querying database if isDirty is True.

    Set holds not Tag or Node objects, but its identities. You should manually
    query library for actual Tag or Node object.
    """

    elementAppeared = pyqtSignal(object)
    elementDisappeared = pyqtSignal(object)
    elementUpdated = pyqtSignal(object, object)  # first - new element value, second - the old one
    resetted = pyqtSignal()

    def __init__(self, lib, query):
        QObject.__init__(self)
        Lockable.__init__(self)
        self.__query = query
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
            return self.__query

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
                        self.fetch()
                        self.resetted.emit()
                    self.isDirty = False
                    self.__isPaused = True

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
            if not self.isFetched:
                self.fetch()
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

    def __iter__(self):
        return _SetIterator(self)

    @property
    def needUpdate(self):
        """Check if Set should update result list.
        """

        with self.lock:
            return self.isFetched and (not self.isPaused or not self.isDirty)


class TagSet(_Set):
    def __init__(self, lib, query):
        _Set.__init__(self, lib, query)
        self.lib.tagCreated.connect(self.onTagCreated, Qt.QueuedConnection)
        self.lib.tagRemoved.connect(self.onTagRemoved, Qt.QueuedConnection)
        self.lib.tagUpdated.connect(self.onTagUpdated, Qt.QueuedConnection)
        self.lib.linkCreated.connect(self.onLinkCreated, Qt.QueuedConnection)
        self.lib.linkRemoved.connect(self.onLinkRemoved, Qt.QueuedConnection)

    def _fetch(self):
        with self.lock:
            self._results = self.lib.tags(self.query)

    def onTagCreated(self, new_tag):
        # when tag is created it can appear in set
        with self.lock:
            if self.needUpdate:
                if self.query.passes(new_tag):
                    self._results.append(new_tag)
                    self.elementAppeared.emit(new_tag)
            elif not self.isDirty:
                if self.query.passes(new_tag):
                    self.isDirty = True

    def onTagRemoved(self, removed_tag):
        with self.lock:
            if self.needUpdate:
                if removed_tag in self._results:
                    self._results = [x for x in self._results if x != removed_tag]
                    self.elementDisappeared.emit(removed_tag)
            elif not self.isDirty:
                if removed_tag in self._results:
                    self.isDirty = True

    def onTagUpdated(self, updated_tag):
        with self.lock:
            if self.needUpdate:
                if updated_tag in self._results:
                    if not self.query.passes(updated_tag):
                        self._results = [x for x in self._results if x != updated_tag]
                        self.elementDisappeared.emit(updated_tag)
                    else:
                        self.elementUpdated.emit(updated_tag)
                else:
                    if self.query.passes(updated_tag):
                        self._results.append(updated_tag)
                        self.elementAppeared.emit(updated_tag)
            elif not self.isDirty:
                if updated_tag in self._results or self.query.passes(updated_tag):
                    self.isDirty = True

    def __onLink(self, node, tag):
        self.onTagUpdated(tag)

    def onLinkCreated(self, node, tag):
        self.__onLink(node, tag)

    def onLinkRemoved(self, node, tag):
        self.__onLink(node, tag)


class ObjectSet(_Set):
    def __init__(self, lib, query):
        _Set.__init__(self, lib, query)
        self.lib.nodeUpdated.connect(self.onNodeUpdated, Qt.QueuedConnection)
        self.lib.nodeCreated.connect(self.onNodeCreated, Qt.QueuedConnection)
        self.lib.nodeRemoved.connect(self.onNodeRemoved, Qt.QueuedConnection)
        self.lib.linkCreated.connect(self.onLinkCreated, Qt.QueuedConnection)
        self.lib.linkRemoved.connect(self.onLinkRemoved, Qt.QueuedConnection)
        self.lib.tagUpdated.connect(self.onTagUpdated, Qt.QueuedConnection)

    def _fetch(self):
        with self.lock:
            self._results = self.lib.objects(self.query)

    def onNodeUpdated(self, updated_node):
        with self.lock:
            if self.needUpdate:
                if updated_node in self._results:
                    if not self.query.passes(updated_node):
                        self._results = [n for n in self._results if n != updated_node]
                        self.elementAppeared.emit(updated_node)
                    else:
                        self.elementUpdated.emit(updated_node)
                elif self.query.passes(updated_node):
                    self._results.append(updated_node)
                    self.elementAppeared.emit(updated_node)
            elif not self.isDirty:
                if updated_node in self._results or self.query.passes(updated_node):
                    self.isDirty = True

    def onNodeCreated(self, created_node):
        with self.lock:
            if self.needUpdate:
                if self.query.passes(created_node):
                    self._results.append(created_node)
                    self.elementAppeared.emit(created_node)
            elif not self.isDirty:
                if self.query.passes(created_node):
                    self.isDirty = True

    def onNodeRemoved(self, removed_node):
        with self.lock:
            if self.needUpdate:
                if removed_node in self._results:
                    self._results = [n for n in self._results if n != removed_node]
                    self.elementDisappeared.emit(removed_node)
            elif not self.isDirty:
                if removed_node in self._results:
                    self.isDirty = True

    def onLinkCreated(self, node, tag):
        self.__onLink(node, tag)

    def onLinkRemoved(self, node, tag):
        self.__onLink(node, tag)

    def __onLink(self, node, tag):
        self.onNodeUpdated(node)

    def onTagUpdated(self, updated_tag):
        with self.lock:
            # get nodes this tag linked with
            for node in self.lib.nodes(linked_with=updated_tag):
                self.onNodeUpdated(node)
