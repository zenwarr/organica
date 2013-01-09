import os
import sys
import sqlite3
import logging
import uuid
from copy import copy, deepcopy

from PyQt4.QtCore import QObject, pyqtSignal

import organica.utils.helpers as helpers
from organica.utils.lockable import Lockable
from organica.lib.filters import Wildcard, generateSqlCompare, TagQuery, NodeQuery
from organica.lib.objects import (Node, Tag, TagClass, TagValue, isCorrectIdent, Identity,
                                  ObjectError)


logger = logging.getLogger(__name__)


class LibraryError(Exception):
    pass


class Library(QObject, Lockable):
    class Cursor(object):
        def __init__(self, lib):
            self._lib = lib

        def __enter__(self):
            self._cursor = self._lib.connection.cursor()
            return self._cursor

        def __exit__(self, tp, v, tb):
            self._cursor.close()

    class Transaction(object):
        def __init__(self, lib):
            self.lib = lib

        def __enter__(self):
            self.lib._begin()
            self.cursor = self.lib.connection.cursor()
            return self.cursor

        def __exit__(self, exc_type, exc_value, traceback):
            if exc_type is not None:
                self.lib._rollback()
            else:
                self.lib._commit()
            self.cursor.close()

    __ATTRS_TO_SAVE_ON_TRANSACTION = [
        '_meta', '_tagClasses', '_tags', '_nodes'
    ]

    # Signals are emitted when set of library objects is changed or updated.
    # Receiver should not rely on library state at moment of processing signal as
    # it can be caused by changes made by another thread. Arguments values should
    # be used instead (all passed values are copies of original objects)

    # emitted after library has returned to previous state on rollbacking transaction
    resetted = pyqtSignal()

    # emitted after any operation has changed metas. Argument is dictionary of metas after modifications
    metaChanged = pyqtSignal(object)

    tagCreated = pyqtSignal(Tag)
    tagRemoved = pyqtSignal(Tag)
    tagUpdated = pyqtSignal(Tag, Tag)

    nodeUpdated = pyqtSignal(Node, Node)
    nodeCreated = pyqtSignal(Node)
    nodeRemoved = pyqtSignal(Node)

    linkCreated = pyqtSignal(Node, Tag)
    linkRemoved = pyqtSignal(Node, Tag)

    def __init__(self):
        QObject.__init__(self)
        Lockable.__init__(self)
        self._conn = None
        self._filename = ''
        self._meta = {}  # map by name
        self._tagClasses = {}  # map by name
        self._tags = {}  # map by id
        self._nodes = {}  # map by id
        self._trans_states = []

    @staticmethod
    def loadLibrary(filename):
        """Load library from database file. File should exists, otherwise LibraryError raised.
        To create in-memory database, use createLibrary instead.
        """

        if filename.casefold() == ':memory:':
            raise LibraryObject('Library.createLibrary should be used to create in-memory databases')

        if not os.path.exists(filename):
            raise LibraryError('database file {0} does not exists'.format(filename))

        lib = Library()
        lib._connect(filename)

        # check magic row to distinguish organica library
        with self.cursor() as c:
            c.execute("select 1 from organica_meta where name = 'organica' and value = 'is magic'")
            if not c.fetchone():
                raise LibraryError('database "{0}" is not organica database'.format(filename))

        # load meta information and tag classes. We always keep all tag classes
        # in memory for quick access
        lib.__loadMeta()
        lib.__loadTagClasses()
        return lib

    @staticmethod
    def createLibrary(filename):
        """Creates new library in file :filename:. If database file does not exists, LibraryError will be
        raised. :filename: can be ":memory:" - in this case in-memory database will be created.
        """

        # we will not replace existing database
        if os.path.exists(filename):
            raise LibraryError('database file "{0}" already exists'.format(filename))

        lib = Library()
        lib._connect(filename)

        # create database schema
        # objects id is autoincrement to avoid collating which can occup as we use
        # tags with OBJECT_REFERENCE type.
        # meta, node and tag class names are not case-sensitive
        # we are storing some tag class parameters in links table to prevent slow
        # queries to tag classes table.
        with lib.cursor() as c:
            c.executescript("""
                    pragma encoding = 'UTF-8';

                    create table organica_meta(name text collate nocase,
                                               value text);

                    create table nodes(id integer primary key autoincrement,
                                       display_name text collate strict_nocase);

                    create table tag_classes(id integer primary key,
                                             name text collate nocase unique,
                                             value_type integer,
                                             hidden integer);

                    create table tags(id integer primary key,
                                      class_id integer,
                                      value_type integer,
                                      value blob,
                                      foreign key(class_id) references tag_classes(id));

                    create table links(node_id integer,
                                       tag_class_id integer,
                                       tag_id integer,
                                       foreign key(node_id) references nodes(id),
                                       foreign key(tag_class_id) references tag_classes(id),
                                       unique(node_id, tag_id));

                    create index tags_index on tags(class_id, value_type, value);

                    create index links_index on links(node_id, tag_class_id, tag_id);

                    create index nodes_index on nodes(display_name);
                            """)

            # and add magic meta
            lib.setMeta('organica', 'is magic')
        return lib

    def getMeta(self, meta_name, default=''):
        """Get meta value. Meta name is not case-sensitive
        """

        with self.lock:
            return self._meta.get(meta_name.casefold(), default)

    def testMeta(self, name_mask):
        """Test if meta with name that matches given mask exists in database.
        """

        with self.lock:
            if isinstance(name_mask, Wildcard):
                return self._meta.contains(lambda x: name_mask == x)
            else:
                return name_mask.casefold() in self._meta

    def setMeta(self, meta_name, meta_value):
        """Writes meta with :meta_name: and :meta_value: to database. :meta_value: is converted to
        string before saving. Meta name should be correct identifier (just like tag class name).
        """

        meta_name = meta_name.casefold()
        meta_value = str(meta_value)
        with self.lock:
            if not isCorrectIdent(meta_name):
                raise LibraryError('invalid meta name {0}'.format(meta_name))

            with self.transaction() as c:
                if meta_name in self._meta:
                    if meta_value != self._meta[meta_name]:
                        c.execute('update organica_meta set value = ? where name = ?',
                                (meta_value, meta_name))
                else:
                    c.execute('insert into organica_meta(name, value) values(?, ?)',
                                (meta_name, meta_value))
                self._meta[meta_name] = meta_value
                self.metaChanged.emit(copy(self._meta))

    def removeMeta(self, name_mask):
        """Remove meta with names matching given mask.
        """

        with self.lock:
            if isinstance(name_mask, Wildcard):
                with self.transaction() as c:
                    c.execute('delete from organica_meta where ' + generateSqlCompare(name_mask))
                    for k in self._meta.keys():
                        if name_mask == k:
                            del self._meta[k]
            else:
                with self.transaction() as c:
                    name_mask = name_mask.casefold()
                    c.execute('delete from organica_meta where name = ?', (str(name_mask), ))
                    del self._meta[str(name_mask)]
            self.metaChanged.emit(dict(self._meta))

    @property
    def allMeta(self):
        """Copy of dictionary containing all metas.
        """

        with self.lock:
            return copy(self._meta)

    def __loadMeta(self):
        """Load (or reload) all meta from database"""

        with self.lock:
            self._meta.clear()
            with self.cursor() as c:
                c.execute("select name, value from organica_meta")
                for r in c.fetchall():
                    if not isCorrectIdent(r[0]):
                        logger.warning('invalid meta name "{0}", ignored'.format(r[0]))
                    else:
                        self._meta[r[0].casefold()] = r[1]

    def __loadTagClasses(self):
        """Load (or reload) all tag classes from database"""

        with self.lock:
            with self.transaction() as c:
                c.execute("select id, name, value_type, hidden from tag_classes")
                for r in c.fetchall():
                    try:
                        tc = TagClass(Idenitty(self, int(r[0])), str(r[1]), int(r[2]), bool(r[3]))
                    except ObjectError:
                        logger.warn('invalid tag class "{0}" (#{1})'.format(r[1], r[0]))
                        continue
                    tc.identity = Identity(self, int(r[0]))
                    self._tagClasses[tc.name.casefold()] = tc

    def tagClass(self, tag_class):
        """Get tag class with given identity or name. Another use is to get actual value of flushed
        class. If class with given identity is not found or identity is invalid, returns None.
        """

        with self.lock:
            if isinstance(tag_class, Identity):
                for tclass in self._tagClasses.values():
                    if tclass.identity == tag_class:
                        return deepcopy(tclass)
                else:
                    return None
            else:
                return deepcopy(self._tagClasses.get(tag_class.casefold(), None))

    def tagClasses(self, name_mask):
        """Get classes with names that matches given mask.
        """

        return [deepcopy(x) for x in self._tagClasses.values() if name_mask == x.name]

    def createTagClass(self, name, value_type=TagValue.TYPE_TEXT, is_hidden=False):
        """Create new class with given name, value type and hidden flag. If another class
        with this name already exists it will be returned only if its value type and hidden
        flag matches given ones. Otherwise LibraryError will be raised.
        """

        with self.lock:
            try:
                tc = TagClass(Identity(), str(name), int(value_type), bool(is_hidden))
            except ObjectError:
                raise TypeError('invalid arguments')

            # check if we have another class with this name. We can return existing
            # tag class only if one is exact copy of given class
            existing_class = self.tagClass(name)
            if existing_class:
                if existing_class.valueType == value_type and existing_class.hidden == is_hidden:
                    return existing_class
                else:
                    raise LibraryError('tag class with name "{0}" already exists'.format(name))

            with self.transaction() as c:
                c.execute('insert into tag_classes(name, value_type, hidden) ' \
                          'values(?, ?, ?)', (str(name), int(value_type), bool(is_hidden)))
                tc.identity = Identity(self, c.lastrowid)

            # update cached
            self._tagClasses[tc.name.casefold()] = deepcopy(tc)
            return tc

    getOrCreateTagClass = createTagClass

    def removeTagClass(self, tag_class, remove_tags=False):
        """Remove class by name or Identity. If :remove_tags: is True, all tags with this
        class will also be removed. Otherwise LibraryError will be raised if there are any
        tags with this class.
        """

        with self.lock:
            if isinstance(tag_class, str):
                tag_class = self.tagClass(tag_class)

            if tag_class is None or not tag_class.isFlushed or tag_class.lib is not self:
                raise TypeError('invalid argument: tag_class')

            r_class = self.tagClass(tag_class)
            if not r_class:
                raise LibraryError('no tag class #{0} found'.format(tag_class.id))

            # remove tags or ensure there is no them
            if remove_tags:
                self.removeTags(TagQuery(tag_class=tag_class))
            elif self.tags(TagQuery(tag_class=tag_class)):
                raise LibraryError('cannot remove class while there are tags using it')

            with self.transaction() as c:
                c.execute('delete from tag_classes where id = ?', (tag_class.id, ))

            # update cache
            del self._tagClasses[r_class.name.casefold()]

    def _tagsFromQuery(self, cursor):
        """Get tag list from query results. Assume that rows are (id, class_id, value_type, value)
        """

        with self.lock:
            r = []
            for row in cursor.fetchall():
                if row[0] in self._tags:
                    # if we have tag in cache, return it
                    r.append(deepcopy(self._tags[row[0]]))
                else:
                    # otherwise create new tag and encache it
                    tag_class = self.tagClass(Identity(self, int(row[1])))
                    if tag_class is None:
                        logger.log('invalid class_id for tag #{0}'.format(row[0]))
                        continue
                    try:
                        tag = Tag(tag_class, TagValue.fromDatabaseForm(tag_class, row[3]))
                    except (TypeError, ObjectError):
                        logger.log('invalid tag #{0}'.format(row[0]))
                        continue
                    tag.identity = Identity(self, int(row[0]))
                    self._tags[tag.id] = deepcopy(tag)
                    r.append(tag)
            return r

    def tags(self, query):
        """Query database for tags. :query: should be TagQuery object.
        """

        if query is None or query.qeval() == 0:
            return []

        with self.lock:
            sql = 'select id, class_id, value_type, value from tags'
            if query.qeval() == -1:
                sql = sql + ' where ' + query.generateSqlWhere()
            with self.cursor() as c:
                c.execute(sql)
                return self._tagsFromQuery(c)

    def tag(self, tag):
        """Get tag with given identity or actual value of tag.
        """

        if tag is None or not tag.isFlushed or tag.lib is not self:
            return None

        if tag.id in self._tags:
            return deepcopy(self._tags[tag.id])
        else:
            r = self.tags(TagQuery(identity=tag))
            return r[0] if r else None

    def createTag(self, tag_class, value):
        """Create new tag with given class and value. Class can be string or class Identity.
        If database has another tag with given class and value, it will be returned.
        """

        with self.lock:
            if isinstance(tag_class, str):
                tag_class = self.tagClass(tag_class)
            elif isinstance(tag_class, Identity):
                tag_class = self.tagClass(tag_class)

            try:
                tag = Tag(tag_class, value)
            except (TypeError, ObjectError):
                raise TypeError('invalid arguments')

            # check if we already have duplicate of this tag, in this case
            # return value of existing tag
            existing_tags = self.tags(TagQuery(tag_class=tag_class, value=value))
            if existing_tags:
                return existing_tags[0]

            with self.transaction() as c:
                c.execute('insert into tags(class_id, value_type, value) values(?, ?, ?)',
                          (int(tag_class.id), int(tag_class.valueType), value.databaseForm()))
                tag.identity = Identity(self, c.lastrowid)

            # encache it
            self._tags[tag.id] = deepcopy(tag)

            # and notify
            self.tagCreated.emit(deepcopy(tag))
            return tag

    getOrCreateTag = createTag

    def flushTag(self, tag_to_flush):
        """Flushes tag into database.
        """

        with self.lock:
            old_tag = self.tag(tag_to_flush.identity)

            if old_tag is None:
                return self.createTag(tag_to_flush.tagClass, tag_to_flush.value)
            else:
                if old_tag != tag_to_flush:
                    with self.transaction() as c:
                        c.execute('update tags set value = ?, class_id = ? where id = ?',
                                  (tag_to_flush.value.databaseForm(), tag_to_flush.tagClass.id, tag_to_flush.id))

                        if tag_to_flush.tagClass.valueType != old_tag.tagClass.valueType:
                            c.execute('update links set tag_class_id = ? where tag_id = ?',
                                      (tag_to_flush.tagClass.id, tag_to_flush.id))

                    self._tags[tag_to_flush.id] = deepcopy(tag_to_flush)

                    # update also cached nodes that depend on this tag. Node.updateTag
                    # method will replace saved tag value with new one, but will not
                    # query database if tags are not fetched. So we cannot determine
                    # which nodes depeneds on this tag and should call updateTag for each node.
                    for node in self._nodes.values():
                        node.updateTag(tag_to_flush)

                    self.tagUpdated.emit(deepcopy(tag_to_flush), deepcopy(old_tag))

                    return tag_to_flush

    def removeTag(self, tag_to_remove, remove_links=False):
        """Remove tag from database. If :remove_links: is True, all links to this Tag will removed,
        otherwise LibraryError will raised if tag is used.
        Note the difference between removeTag and removeTags - this method only accepts Identity (or Tag).
        """

        with self.lock:
            if tag_to_remove is None or not tag_to_remove.isFlushed or tag_to_remove.lib is not self:
                raise TypeError('invalid argument: tag_to_remove')

            # get actual value of this tag
            if not self.tag(tag):
                raise LibraryError('tag does not exists: #{0}'.format(tag_to_remove.id))

            with self.transaction() as c:
                if remove_links:
                    for node in self.nodes(NodeQuery(tags=TagQuery(identity=tag_to_remove))):
                        self.removeLink(node, tag_to_remove)
                elif self.nodes(NodeQuery(tags=TagQuery(identity=tag_to_remove))):
                    raise LibraryError('cannot remove tag while there are nodes linked with it')

                c.execute('delete from tags where id = ?', (tag.id, ))

            # update cache
            if tag.id in self._tags:
                self._tags.remove(tag.id)

            # notify about tag
            self.tagRemoved.emit(deepcopy(tag_to_remove))

    def removeTags(self, tag_query, remove_links=False):
        """Remove tags from database.
        """

        with self.lock:
            for tag in self.tags(tag_query):
                self.removeTag(tag, remove_links)

    def createNode(self, display_name_template, tags=None):
        """Create new node with given display name. Optionally links all tags from sequence.
        Sequence should contains Tag objects and tuples (class or class name, value).
        Tag objects from sequence will be flushed.
        """

        with self.lock:
            try:
                node = Node(display_name_template)
            except ObjectError:
                raise TypeError('invalid arguments')

            with self.transaction() as c:
                c.execute('insert into nodes(display_name) values (?)',
                                (str(node.displayNameTemplate), ))
                node.identity = Identity(self, c.lastrowid)

                self._nodes[node.id] = deepcopy(node)

                self.nodeCreated.emit(deepcopy(node))

                # link given tags
                if tags:
                    for tag in tags:
                        if isinstance(tag, tuple):
                            tag = self.createTag(tag[0], tag[1])
                        else:
                            tag.flush(self)
                        self.createLink(node, tag)

            return node

    def removeNode(self, node_to_remove, remove_references=False):
        """Remove node from database. If :remove_references: is True, all tags with TYPE_NODE_REFERENCE
        will be removed from database. Otherwise LibraryError will be raised if such tags exist.
        Links will be removed first (with any value of :remove_references:)
        Note the difference between this method and removeNodes, this method accepts only Identity (or Node).
        """

        with self.lock:
            if node is None or not node.isFlushed or node.lib is not self:
                raise TypeError('invalid argument: node')

            if not self.node(node_to_remove):
                raise LibraryError('node #{0} does not exists'.format(node_to_remove.id))

            with self.transaction() as c:
                if remove_references:
                    self.removeTags(TagQuery(node_ref=node_to_remove))
                elif self.tags(TagQuery(node_ref=node_to_remove)):
                    raise LibraryError('cannot remove node while there are references to it')

                c.execute('delete from links where node_id = ?', (node_to_remove.id,))
                c.execute('delete from nodes where id = ?', (node_to_remove.id,))

            # update cache
            if node_to_remove.id in self._nodes:
                del self._nodes[obj.id]

            # notify about node
            self.nodeRemoved.emit(deepcopy(node_to_remove))

    def removeNodes(self, node_query, remove_references=False):
        """Remove nodes that match given query.
        """

        # remove nodes that pass given filter
        with self.lock:
            for node in self.nodes(node_query):
                self.removeNode(node, remove_references)

    def nodeTags(self, node):
        """Fetch tags that linked with node. This is convenience method.
        """

        return self.tags(TagQuery(linked_with=node))

    def nodes(self, query):
        """Get nodes from query.
        """

        if not query or query.qeval() == 0:
            return None

        sql = 'select id, display_name from nodes'
        if query.qeval() == -1:
            sql = sql + ' where ' + query.generateSqlWhere()
        with self.cursor() as c:
            c.execute(sql)
            return self._nodesFromQuery(c)

    def node(self, node):
        """Get node with given identity or actual value of node.
        """

        with self.lock:
            if node.id in self._nodes:
                return deepcopy(self._nodes[node.id])
            else:
                r = self.nodes(NodeQuery(identity=node))
                return r[0] if r else None

    def flushNode(self, node_to_flush):
        """Flush node into database
        """

        with self.lock:
            unmod_node = self.node(node_to_flush)
            if not unmod_node:
                return self.createNode(node_to_flush.displayNameTemplate,
                                                         node_to_flush.allTags)
            else:
                # find links to delete and to create. Flush already linked tags.
                tagsToUnlink = []
                tagsToLink = []
                tagsToFlush = []
                actualTags = []

                for linked_tag in unmod_node.allTags:
                    if not node_to_flush.testTag(linked_tag.identity):
                        tagsToUnlink.append(linked_tag)
                    else:
                        tagsToFlush.append(linked_tag)

                for tag in node_to_flush.allTags:
                    if not tag.isFlushed or not unmod_node.testTag(tag.identity):
                        tagsToLink.append(tag)

                with self.transaction() as c:
                    if node_to_flush.displayNameTemplate != unmod_node.displayNameTemplate:
                        c.execute('update nodes set display_name = ? where id = ?',
                                (node_to_flush.displayNameTemplate, node_to_flush.id))

                        self.nodeUpdated.emit(deepcopy(unmod_node), deepcopy(node_to_flush))

                        if node_to_flush.id in self._nodes:
                            self._nodes[node_to_flush.id].displayNameTemplate = \
                                        node_to_flush.displayNameTemplate

                    for tag in tagsToUnlink:
                        self.removeLink(node_to_flush, tag)

                    for tag in tagsToLink:
                        actualTags.append(tag.flush(self))
                        self.createLink(node_to_flush, tag)

                    for tag in tagsToFlush:
                        actualTags.append(tag.flush(self))

                actualNode = Node(node_to_flush.displayNameTemplate, actualTags)
                actualNode.identity = node_to_flush.identity
                return actualNode

    def createLink(self, node, tag):
        """Create link between node and tag.
        """

        if node is None or not node.isFlushed or tag is None or not tag.isFlushed or \
                node.lib is not self or tag.lib is not self:
            raise TypeError('invalid arguments')

        with self.lock:
            if self.node(node) is None or self.tag(tag) is None:
                raise LibraryError('node or tag does not exist')

            node = self.node(node)
            if node.testTag(tag):
                raise LibraryError('link between node #{0} and tag #{1} already exists' \
                                   .format(node.id, tag.id))
            node.ensureTagsFetched()

            with self.transaction() as c:
                c.execute('insert into links(node_id, tag_id, tag_class_id) values (?, ?, ?)',
                          (node.id, tag.id, tag.tagClass.id))

            node.setAllTags(node.allTags + [tag])
            self._nodes[node.id] = deepcopy(node)

            self.linkCreated.emit(deepcopy(node), deepcopy(tag))

    def removeLink(self, node, tag):
        """Remove link between node and tag. Silently returns if no link between them exist.
        """

        if node is None or tag is None or not node.isFlushed or not tag.isFlushed or \
                node.lib is not self or tag.lib is not self:
            raise TypeError('invalid arguments')

        with self.lock:
            if not self.node(node) or not self.tag(tag):
                raise LibraryError('node or tag does not exist')

            node = self.node(node)
            if not node.testTag(tag):
                raise LibraryError('link between node #{0} and tag #{1} does not exist' \
                                   .format(node.id, tag.id))
            node.ensureTagsFetched()

            with self.transaction() as c:
                c.execute('delete from links where node_id = ? and tag_id = ?',
                          (node.id, tag.id))

            node.setAllTags([t for t in node.allTags if t.identity != tag.identity])
            self._nodes[node.id] = deepcopy(node)

            self.linkRemoved.emit(deepcopy(node), deepcopy(tag))

    def _nodesFromQuery(self, cursor):
        """Get node list from SQL query results. Assumes that columns are (id, display_name)
        """

        r = []
        for row in cursor.fetchall():
            if int(row[0]) in self._nodes:
                r.append(deepcopy(self._nodes[row[0]]))
            else:
                node = Node(row[1])
                node.identity = Identity(self, row[0])
                self._nodes[node.id] = node
                r.append(deepcopy(node))
        return r

    def remove(self, lib_object):
        if isinstance(lib_object, TagClass):
            self.removeTagClass(lib_object)
        elif isinstance(lib_object, Tag):
            self.removeTag(lib_object)
        elif isinstance(lib_object, Node):
            self.removeNode(lib_object)
        else:
            raise ValueError()

    def flush(self, lib_object):
        if isinstance(lib_object, Tag):
            self.flushTag(lib_object)
        elif isinstance(lib_object, Node):
            self.flushNode(lib_object)
        else:
            raise ValueError()

    @property
    def connection(self):
        with self.lock:
            return self._conn

    def disconnect(self):
        with self.lock:
            if self._conn:
                self._conn.close()

    @property
    def databaseFilename(self):
        with self.lock:
            return self._filename

    def transaction(self):
        return self.Transaction(self)

    def cursor(self):
        return self.Cursor(self)

    def _begin(self):
        self.lock.acquire()  # create additional lock to block other threads
        self.__savestate()
        self.connection.execute('savepoint xs')

    def _commit(self):
        assert(self._trans_states)
        self._trans_states.pop()
        self.connection.execute('release xs')
        self.lock.release()

    def _rollback(self):
        self.__restorestate()
        self.connection.execute('rollback to xs')
        self.connection.execute('release xs')
        self.lock.release()

    def __savestate(self):
        state = {}
        for attr in self.__ATTRS_TO_SAVE_ON_TRANSACTION:
            state[attr] = getattr(self, attr)
        self._trans_states.append(state)

    def __restorestate(self):
        assert(self._trans_states)
        state = self._trans_states.pop()
        for attr in state.keys():
            setattr(self, attr, state[attr])
        self.resetted.emit()

    def _connect(self, filename):
        def strict_nocase_collation(left, right):
            return left.casefold() == right.casefold()

        self._conn = sqlite3.connect(filename, isolation_level=None)
        self._conn.create_collation('strict_nocase', strict_nocase_collation)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('pragma foreign_keys = on')

    def dump(self):
        with self.lock:
            with self.cursor() as c:
                for table in ('organica_meta', 'tag_classes', 'tags', 'nodes', 'links'):
                    c.execute('select * from ' + table)

                    print('#### {0}:'.format(table))

                    columns = [x[0] for x in c.description]
                    print('\t'.join(columns))

                    r = c.fetchone()
                    while r:
                        for column in columns:
                            print(r[column], end="\t")
                        print('')
                        r = c.fetchone()

                    print('')
