import os
import sqlite3
import logging
import copy
import threading
from PyQt4.QtCore import QObject, pyqtSignal, QFileInfo
from organica.utils.lockable import Lockable
from organica.lib.filters import Wildcard, generateSqlCompare, TagQuery, NodeQuery
from organica.lib.objects import Node, Tag, TagClass, TagValue, isCorrectIdent, Identity, ObjectError, get_identity
from organica.lib.storage import LocalStorage
from organica.lib.locator import Locator
import organica.utils.helpers as helpers


logger = logging.getLogger(__name__)


class LibraryError(Exception):
    pass


class LibraryStatistics(object):
    def __init__(self):
        self.classesCount = 0
        self.tagsCount = 0
        self.nodesCount = 0
        self.databaseSize = 0


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

    _AttrsToSaveOnTransaction = ['_meta', '_tagClasses', '_tags', '_nodes']

    _loaded_libraries = []
    _loaded_libraries_lock = threading.RLock()

    LocatorClassName = 'locator'

    MetaName = 'name'
    MetaStoragePath = 'storage_path'
    MetaProfileUuid = 'profile'
    MetaAutoDeleteUnusedTags = 'autodelete_tags'

    # Signals are emitted when set of library objects is changed or updated.
    # Receiver should not rely on library state at moment of processing signal as
    # it can be caused by changes made by another thread. Arguments should
    # be used instead (all passed values are deep copies of original objects)

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

    classCreated = pyqtSignal(TagClass)
    classRemoved = pyqtSignal(TagClass)

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
        self._storage = None

    @staticmethod
    def loadLibrary(filename):
        """Load library from database file. File should exists, otherwise LibraryError raised.
        To create in-memory database, use createLibrary instead.
        """

        if filename.lower() == ':memory:':
            raise LibraryError('Library.createLibrary should be used to create in-memory databases')

        loaded_lib = Library._findOpenLibrary(filename)
        if loaded_lib is not None:
            return loaded_lib

        if not os.path.exists(filename):
            raise LibraryError('database file {0} does not exists'.format(filename))

        lib = Library()
        lib._connect(filename)

        # check magic row to distinguish organica library
        with lib.cursor() as c:
            c.execute("select 1 from organica_meta where name = 'organica' and value = 'is magic'")
            if not c.fetchone():
                raise LibraryError('database "{0}" is not organica database'.format(filename))

        # load meta information and tag classes. We always keep all tag classes
        # in memory for quick access
        lib.__loadMeta()
        lib.__loadTagClasses()

        # load storage if any
        if lib.testMeta(Library.MetaStoragePath):
            storage_path = lib.getMeta(Library.MetaStoragePath)
            if storage_path:
                # relative paths are resolved basing on library path
                if not os.path.isabs(storage_path):
                    storage_path = os.path.join(os.path.dirname(lib.databaseFilename), storage_path)
                if not os.path.exists(storage_path):
                    logger.warning('associated storage directory does not exist: {0}'.format(storage_path))
                else:
                    # do not load storage when its directory does not exist - storage settings will not be loaded.
                    lib._storage = LocalStorage.fromDirectory(storage_path)

        with Library._loaded_libraries_lock:
            Library._loaded_libraries.append(lib)

        return lib

    @staticmethod
    def createLibrary(filename):
        """Creates new library in file :filename:. If database file does not exists, LibraryError will be
        raised. :filename: can be ":memory:" - in this case in-memory database will be created.
        """

        if filename.lower() != ':memory:':
            if Library._findOpenLibrary(filename):
                raise LibraryError('failed to create library {0}: database already in use')

        # we will not replace existing database
        if os.path.exists(filename):
            raise LibraryError('database file "{0}" already exists'.format(filename))

        lib = Library()
        lib._connect(filename)

        # create database schema
        # objects id is autoincrement to avoid collating which can occupy as we use tags with OBJECT_REFERENCE type.
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
                                      use_count integer,
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

            # create basic tag classes
            lib.createTagClass('locator', TagValue.TYPE_LOCATOR)

        with Library._loaded_libraries_lock:
            Library._loaded_libraries.append(lib)

        return lib

    @staticmethod
    def _findOpenLibrary(filename):
        with Library._loaded_libraries_lock:
            for lib in Library._loaded_libraries:
                if QFileInfo(lib.databaseFilename) == QFileInfo(filename):
                    return lib
        return None

    def getMeta(self, meta_name, default=''):
        """Get meta value. Meta name is not case-sensitive
        """

        with self.lock:
            return self._meta.get(helpers.uncase(meta_name), default)

    def testMeta(self, name_mask):
        """Test if meta with name that matches given mask exists in database.
        """

        with self.lock:
            if isinstance(name_mask, Wildcard):
                return any(name_mask == x for x in self._meta)
            else:
                return helpers.uncase(name_mask) in self._meta

    def setMeta(self, meta_name, meta_value):
        """Writes meta with :meta_name: and :meta_value: to database. :meta_value: is converted to
        string before saving. Meta name should be correct identifier (just like tag class name).
        """

        meta_name = helpers.uncase(meta_name)
        if not isCorrectIdent(meta_name):
            raise LibraryError('invalid meta name {0}'.format(meta_name))

        if meta_value is not None:
            meta_value = str(meta_value)

        with self.lock:
            with self.transaction() as c:
                if meta_name in self._meta:
                    if meta_value != self._meta[meta_name]:
                        c.execute('update organica_meta set value = ? where name = ?', (meta_value, meta_name))
                else:
                    c.execute('insert into organica_meta(name, value) values(?, ?)', (meta_name, meta_value))
                self._meta[meta_name] = meta_value
                self.metaChanged.emit(copy.deepcopy(self._meta))

    def removeMeta(self, name_mask):
        """Remove meta with names matching given mask."""

        with self.lock:
            with self.transaction() as c:
                name_mask = helpers.uncase(name_mask)
                c.execute('delete from organica_meta where ' + generateSqlCompare('name', name_mask))
            self._meta = {k: self._meta[k] for k in self._meta.keys() if name_mask != k}
            self.metaChanged.emit(copy.deepcopy(self._meta))

    @property
    def allMeta(self):
        """Copy of dictionary containing all metas."""

        with self.lock:
            return copy.deepcopy(self._meta)

    def __loadMeta(self):
        """Load (or reload) all meta from database"""

        with self.lock:
            self._meta = {}
            with self.cursor() as c:
                c.execute("select name, value from organica_meta")
                for r in c.fetchall():
                    if not isCorrectIdent(r[0]):
                        logger.warning('invalid meta name "{0}", ignored'.format(r[0]))
                    else:
                        self._meta[r[0].lower()] = r[1]

    def __loadTagClasses(self):
        """Load (or reload) all tag classes from database"""

        with self.lock:
            self._tagClasses = dict()
            with self.transaction() as c:
                c.execute("select id, name, value_type, hidden from tag_classes")
                for r in c.fetchall():
                    try:
                        tc = TagClass(Identity(self, int(r[0])), str(r[1]), int(r[2]), bool(r[3]))
                    except ObjectError:
                        logger.error('invalid tag class "{0}" (#{1})'.format(r[1], r[0]))
                        continue
                    self._tagClasses[tc.name.lower()] = tc

    def tagClass(self, tag_class):
        """Get tag class with given identity or name. Another use is to get actual value of flushed
        class. If class with given identity is not found or identity is invalid, returns None.
        """

        with self.lock:
            if isinstance(tag_class, (Identity, TagClass)):
                return helpers.first(copy.deepcopy(tc) for tc in self._tagClasses.values() if
                                     tc.identity == get_identity(tag_class))
            else:
                return copy.deepcopy(self._tagClasses.get(tag_class.lower(), None))

    def tagClasses(self, name_mask=Wildcard('*')):
        """Get classes with names that matches given mask."""

        return [copy.deepcopy(x) for x in self._tagClasses.values() if name_mask == x.name]

    def createTagClass(self, name, value_type=TagValue.TYPE_TEXT, is_hidden=False):
        """Create new class with given name, value type and hidden flag. If another class
        with this name already exists it will be returned only if its value type and hidden
        flag matches given ones. Otherwise LibraryError will be raised.
        """

        with self.lock:
            try:
                tc = TagClass(Identity(), str(name), int(value_type), bool(is_hidden))
            except ObjectError as err:
                raise TypeError('invalid arguments ({0})'.format(err))

            # check if we have another class with this name. We can return existing
            # tag class only if one is exact copy of given class
            existing_class = self.tagClass(name)
            if existing_class:
                if existing_class != tc:
                    raise LibraryError('tag class with name "{0}" already exists'.format(name))
                return existing_class

            with self.transaction() as c:
                c.execute('insert into tag_classes(name, value_type, hidden) values(?, ?, ?)',
                          (str(name), int(value_type), bool(is_hidden)))
                tc.identity = Identity(self, c.lastrowid)

            # update cached
            self._tagClasses[tc.name.lower()] = copy.deepcopy(tc)
            self.classCreated.emit(copy.deepcopy(tc))
            return tc

    def removeTagClass(self, tag_class, remove_tags=False):
        """Remove class by name or Identity. If :remove_tags: is True, all tags with this
        class will also be removed. Otherwise LibraryError will be raised if there are any
        tags with this class.
        """

        with self.lock:
            if not isinstance(tag_class, TagClass):
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
            del self._tagClasses[r_class.name.lower()]

            self.classRemoved.emit(copy.deepcopy(tag_class))

    def tags(self, query):
        """Query database for tags. :query: should be TagQuery object."""

        if query is None or query.qeval() == 0:
            return []

        with self.lock:
            sql = 'select id, class_id, value_type, value, use_count from tags'
            if query.qeval() == -1:
                sql = sql + ' where ' + query.generateSqlWhere()
            with self.cursor() as c:
                c.execute(sql)

                r = []
                for row in c.fetchall():
                    if int(row[0]) not in self._tags:
                        tag_class = self.tagClass(Identity(self, int(row[1])))
                        if tag_class is None:
                            logger.error('invalid class_id for tag #{0}'.format(row[0]))
                            continue
                        try:
                            use_count = row[4]
                            use_count = int(use_count) if use_count is not None else 0
                            tag = Tag(tag_class, TagValue.fromDatabaseForm(tag_class, row[3]), use_count)
                        except (TypeError, ObjectError):
                            logger.error('invalid tag #{0}'.format(row[0]))
                            continue
                        tag.identity = Identity(self, int(row[0]))
                        self._tags[tag.id] = tag
                    r.append(copy.deepcopy(self._tags[int(row[0])]))
                return r

    def tag(self, *args):
        """Get actual value of tag. Can accept one argument - Identity or Tag or
        two arguments - TagClass (str) and TagValue (or TagValue convertible type)
        """

        if len(args) == 1:
            tag = args[0]

            if tag is None or not tag.isFlushed or tag.lib is not self:
                return None

            if tag.id in self._tags:
                return copy.deepcopy(self._tags[tag.id])
            else:
                return helpers.first(self.tags(TagQuery(identity=tag)))
        elif len(args) == 2:
            return helpers.first(self.tags(TagQuery(tag_class=args[0], value=args[1])))
        else:
            raise TypeError('Library.tag should get 1 or 2 arguments, but {0} given'.format(len(args)))

    def createTag(self, tag_class, value):
        """Create new tag with given class and value. Class can be string or class Identity.
        If database has another tag with given class and value, it will be returned.
        """

        with self.lock:
            if not isinstance(tag_class, TagClass):
                tag_class = self.tagClass(tag_class)

            try:
                value = TagValue(value)
                tag = Tag(tag_class, value)
            except (TypeError, ObjectError):
                raise TypeError('invalid arguments')

            # check if we already have duplicate of this tag, in this case
            # return value of existing tag
            existing_tag = self.tag(tag_class, value)
            if existing_tag:
                return existing_tag

            with self.transaction() as c:
                c.execute('insert into tags(class_id, value_type, value, use_count) values(?, ?, ?, ?)',
                          (int(tag_class.id), int(tag_class.valueType), str(value.databaseForm), 0))
                tag.identity = Identity(self, c.lastrowid)

            tag_copy = copy.deepcopy(tag)
            tag_copy.useCount = 0  # sanitize useCount as we use it internally
            self._tags[tag.id] = tag_copy

            # and notify
            self.tagCreated.emit(copy.deepcopy(tag))

            return tag

    def flushTag(self, tag_to_flush):
        """Flush tag into database."""

        if tag_to_flush is None or (tag_to_flush.isFlushed and tag_to_flush.lib is not self):
            raise TypeError('invalid argument: tag_to_flush')

        with self.lock:
            old_tag = self.tag(tag_to_flush.identity)

            if old_tag is None:
                tag_to_flush.identity = self.createTag(tag_to_flush.tagClass, tag_to_flush.value).identity
            else:
                if old_tag != tag_to_flush:
                    if old_tag.tagClass.valueType != tag_to_flush.tagClass.valueType:
                        raise ObjectError('tag value type cannot be changed')

                    with self.transaction() as c:
                        c.execute('update tags set value = ?, class_id = ? where id = ?',
                                  (tag_to_flush.value.databaseForm, tag_to_flush.tagClass.id, tag_to_flush.id))

                        if tag_to_flush.tagClass != old_tag.tagClass:
                            c.execute('update links set tag_class_id = ? where tag_id = ?',
                                      (tag_to_flush.tagClass.id, tag_to_flush.id))

                    tag_copy = copy.deepcopy(tag_to_flush)
                    tag_copy.useCount = old_tag.useCount
                    self._tags[tag_to_flush.id] = tag_copy

                    # update also cached nodes that depend on this tag. Node.updateTag
                    # method will replace saved tag value with new one, but will not
                    # query database if tags are not fetched. So we cannot determine
                    # which nodes depeneds on this tag and should call updateTag for each node.
                    for node in self._nodes.values():
                        node.updateTag(tag_copy)

                    self.tagUpdated.emit(copy.deepcopy(self._tags[tag_to_flush.id]), copy.deepcopy(old_tag))

            return tag_to_flush

    def removeTag(self, tag_to_remove, remove_links=False):
        """Remove tag from database. If :remove_links: is True, all links to this Tag will removed,
        otherwise LibraryError will raised if tag is used.
        Note the difference between removeTag and removeTags - this method only accepts Identity (or Tag).
        """

        if tag_to_remove is None or not tag_to_remove.isFlushed or tag_to_remove.lib is not self:
            raise TypeError('invalid argument: tag_to_remove')

        with self.lock:
            unmodified_tag = self.tag(tag_to_remove)
            if not unmodified_tag:
                raise LibraryError('tag does not exists: #{0}'.format(tag_to_remove.id))

            with self.transaction() as c:
                if remove_links:
                    for node in self.nodes(NodeQuery(tags=TagQuery(identity=tag_to_remove))):
                        self.removeLink(node, tag_to_remove)
                elif unmodified_tag.useCount != 0:
                     raise LibraryError('cannot remove tag while there are nodes linked with it')

                c.execute('delete from tags where id = ?', (tag_to_remove.id, ))

            # update cache
            if tag_to_remove.id in self._tags:
                del self._tags[tag_to_remove.id]

            # notify about tag
            self.tagRemoved.emit(copy.deepcopy(unmodified_tag))

    def removeTagIfUnused(self, tag_to_remove):
        tag_to_remove = self.tag(tag_to_remove)
        if tag_to_remove is not None and tag_to_remove.useCount == 0:
            self.removeTag(tag_to_remove)

    def removeTags(self, tag_query, remove_links=False):
        """Remove tags from database.
        """

        with self.lock:
            for tag in self.tags(tag_query):
                self.removeTag(tag, remove_links)

    def createNode(self, display_name_template, tags=None):
        """Create new node with given display name. Optionally links all tags from sequence.
        Sequence should contains Tag objects and tuples (class or class name, value).
        Tag objects from sequence will not be changed.
        """

        with self.lock:
            try:
                node = Node(display_name_template)
            except ObjectError:
                raise TypeError('invalid arguments')

            with self.transaction() as c:
                c.execute('insert into nodes(display_name) values (?)', (str(node.displayNameTemplate), ))
                node.identity = Identity(self, c.lastrowid)

                self._nodes[node.id] = copy.deepcopy(node)

                self.nodeCreated.emit(copy.deepcopy(node))

                # link given tags
                if tags:
                    for tag in tags:
                        if isinstance(tag, tuple):
                            tag = self.createTag(tag[0], tag[1])
                        else:
                            self.flushTag(tag)
                        self.createLink(node, tag)

            return node

    def removeNode(self, node_to_remove, remove_references=False):
        """Remove node from database. If :remove_references: is True, all tags with TYPE_NODE_REFERENCE
        will be removed from database. Otherwise LibraryError will be raised if such tags exist.
        Links will be removed first (with any value of :remove_references:)
        Note the difference between this method and removeNodes, this method accepts only Identity (or Node).
        """

        if node_to_remove is None or not node_to_remove.isFlushed or node_to_remove.lib is not self:
            raise TypeError('invalid argument: node')

        with self.lock:
            node_to_remove = self.node(node_to_remove)
            if not node_to_remove:
                raise LibraryError('node #{0} does not exists'.format(node_to_remove.id))

            with self.transaction() as c:
                if remove_references:
                    self.removeTags(TagQuery(node_ref=node_to_remove))
                elif self.tags(TagQuery(node_ref=node_to_remove)):
                    raise LibraryError('cannot remove node while there are references to it')

                for tag in node_to_remove.allTags:
                    self.removeLink(node_to_remove, tag)

                c.execute('delete from nodes where id = ?', (node_to_remove.id,))

            # update cache
            if node_to_remove.id in self._nodes:
                del self._nodes[node_to_remove.id]

            # notify about node
            self.nodeRemoved.emit(copy.deepcopy(node_to_remove))

    def removeNodes(self, node_query, remove_references=False):
        """Remove nodes that match given query.
        """

        # remove nodes that pass given filter
        with self.lock:
            for node in self.nodes(node_query):
                self.removeNode(node, remove_references)

    def nodes(self, query):
        """Get nodes from query.
        """

        if query is None or query.qeval() == 0:
            return []

        sql = 'select id, display_name from nodes'
        if query.qeval() == -1:
            sql = sql + ' where ' + query.generateSqlWhere()
        with self.cursor() as c:
            c.execute(sql)

            r = []
            for row in c.fetchall():
                if int(row[0]) not in self._nodes:
                    node = Node(row[1])
                    node.identity = Identity(self, row[0])
                    node.displayNameTemplate = str(row[1])
                    self._nodes[node.id] = node
                r.append(copy.deepcopy(self._nodes[int(row[0])]))
            return r

    def node(self, node):
        """Get node with given identity or actual value of node.
        """

        with self.lock:
            if node.id in self._nodes:
                return copy.deepcopy(self._nodes[node.id])
            else:
                return helpers.first(self.nodes(NodeQuery(identity=node)))

    def flushNode(self, node_to_flush):
        """Flush node into database. Set of linked tag is changed to match node_to_flush.allTags array.
        """

        if node_to_flush is None or (node_to_flush.isFlushed and node_to_flush.lib is not self):
            raise TypeError('invalid argument: node_to_flush')

        with self.lock:
            unmodified_node = self.node(node_to_flush)
            if not unmodified_node:
                # just create new node if one does not exist. Update only identity.
                node_to_flush.identity = self.createNode(node_to_flush.displayNameTemplate,
                                                         node_to_flush.allTags).identity
            else:
                with self.transaction() as c:
                    if node_to_flush.displayNameTemplate != unmodified_node.displayNameTemplate:
                        c.execute('update nodes set display_name = ? where id = ?',
                                  (node_to_flush.displayNameTemplate, node_to_flush.id))

                        if node_to_flush.id in self._nodes:
                            self._nodes[node_to_flush.id].displayNameTemplate = node_to_flush.displayNameTemplate

                        self.nodeUpdated.emit(self.node(node_to_flush), copy.deepcopy(unmodified_node))

                    # find differences in tag list
                    actual_tags = []  # will contain flushed copies of tags

                    # find tags to flush (tags that are not in unmodified_node.allTags)
                    for tag_to_flush in (tag for tag in node_to_flush.allTags if tag not in unmodified_node.allTags):
                        self.flushTag(tag_to_flush)
                        self.createLinkIfNotExists(node_to_flush, tag_to_flush)
                        actual_tags.append(tag_to_flush)

                    # find tags to remove (tags with identities that are not in node_to_flush.allTags)
                    for tag in unmodified_node.allTags:
                        if tag.identity not in (tag.identity for tag in node_to_flush.allTags):
                            self.removeLinkIfExists(node_to_flush, tag)

                    # append tags that should remain intact
                    actual_tags += (tag for tag in node_to_flush.allTags if tag in unmodified_node.allTags)

                    node_to_flush.allTags = actual_tags

            return node_to_flush

    def createLink(self, node, tag):
        """Create link between node and tag.
        """

        if (node is None or not node.isFlushed or tag is None or not tag.isFlushed or node.lib is not self or
                        tag.lib is not self):
            raise TypeError('invalid arguments')

        with self.lock:
            node = self.node(node)
            tag = self.tag(tag)

            if node is None or tag is None:
                raise LibraryError('node or tag does not exist')

            if node.testTag(tag):
                raise LibraryError('link between node #{0} and tag #{1} already exists'.format(node.id, tag.id))
            node.ensureTagsFetched()  # hold this copy to pass it to signal

            with self.transaction() as c:
                # limit use number for tags of locator class by one
                locator_class = self.tagClass(self.LocatorClassName)
                if locator_class is not None and tag.tagClass == locator_class and tag.useCount > 0:
                    raise LibraryError('tags of special locator class cannot be used more than once')

                c.execute('insert into links(node_id, tag_id, tag_class_id) values (?, ?, ?)',
                          (node.id, tag.id, tag.tagClass.id))

                c.execute('update tags set use_count = use_count + 1 where id = ?', (tag.id, ))

            node.allTags.append(tag)
            self._nodes[node.id] = copy.deepcopy(node)

            if tag.id in self._tags:
                self._tags[tag.id].useCount += 1

            self.linkCreated.emit(copy.deepcopy(node), copy.deepcopy(tag))

    def createLinkIfNotExists(self, node, tag):
        with self.lock:
            actual_node = self.node(node)
            if actual_node is not None and not actual_node.testTag(tag):
                self.createLink(node, tag)

    def removeLink(self, node, tag):
        """Remove link between node and tag.
        """

        if node is None or tag is None or not node.isFlushed or not tag.isFlushed or \
                node.lib is not self or tag.lib is not self:
            raise TypeError('invalid arguments')

        with self.lock:
            node = self.node(node)
            tag = self.tag(tag)

            if node is None or tag is None:
                raise LibraryError('node or tag does not exist')

            if not node.testTag(tag):
                raise LibraryError('link between node #{0} and tag #{1} does not exist'.format(node.id, tag.id))
            node.ensureTagsFetched()

            with self.transaction() as c:
                c.execute('delete from links where node_id = ? and tag_id = ?', (node.id, tag.id))

            # actualize node
            node.allTags = [t for t in node.allTags if t.identity != tag.identity]
            self._nodes[node.id] = node

            if tag.id in self._tags:
                self._tags[tag.id].useCount -= 1

            self.linkRemoved.emit(copy.deepcopy(node), copy.deepcopy(tag))

            if self.autoDeleteUnusedTags:
                self.removeTagIfUnused(tag)

    def removeLinkIfExists(self, node, tag):
        with self.lock:
            actual_node = self.node(node)
            if actual_node is not None and actual_node.testTag(tag):
                self.removeLink(node, tag)

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

    def close(self):
        with self.lock:
            if self._conn:
                self._conn.close()

            with Library._loaded_libraries_lock:
                Library._loaded_libraries = [lib for lib in Library._loaded_libraries if lib is not self]

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
        for attr in self._AttrsToSaveOnTransaction:
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
            l = helpers.uncase(left)
            r = helpers.uncase(right)
            if l == r:
                return 0
            elif l < r:
                return 1
            else:
                return -1

        def match_tagvalue(value, pattern):
            return Wildcard(pattern) == str(TagValue(value))

        self._filename = filename
        self._conn = sqlite3.connect(filename, isolation_level=None)
        self._conn.create_collation('strict_nocase', strict_nocase_collation)
        self._conn.create_function('match_tagvalue', 2, match_tagvalue)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute('pragma foreign_keys = on')

    @property
    def name(self):
        return self.getMeta(self.MetaName)

    @name.setter
    def name(self, new_name):
        self.setMeta(self.MetaName, new_name)

    @property
    def storage(self):
        with self.lock:
            return self._storage

    @storage.setter
    def storage(self, new_storage):
        with self.lock:
            if self._storage == new_storage:
                return

            self._storage = new_storage

            if self._storage is not None and self._storage.rootDirectory:
                self.setMeta(self.MetaStoragePath, self._storage.rootDirectory)
            else:
                self.removeMeta(self.MetaStoragePath)

    @property
    def profileUuid(self):
        with self.lock:
            return self.getMeta(self.MetaProfileUuid) if self.testMeta(self.MetaProfileUuid) else ''

    @profileUuid.setter
    def profileUuid(self, new_uuid):
        self.setMeta(self.MetaProfileUuid, new_uuid)

    def calculateStatistics(self):
        stat = LibraryStatistics()
        with self.lock:
            with self.cursor() as c:
                c.execute('select count(*) from tag_classes')
                stat.classesCount = c.fetchone()[0]

                c.execute('select count(*) from tags')
                stat.tagsCount = c.fetchone()[0]

                c.execute('select count(*) from nodes')
                stat.nodesCount = c.fetchone()[0]

                stat.databaseSize = os.stat(self.databaseFilename).st_size
        return stat

    @property
    def autoDeleteUnusedTags(self):
        saved_meta = self.getMeta(self.MetaAutoDeleteUnusedTags, 0)
        try:
            return bool(int(saved_meta))
        except ValueError:
            return False

    @autoDeleteUnusedTags.setter
    def autoDeleteUnusedTags(self, new_value):
        self.setMeta(self.MetaAutoDeleteUnusedTags, str(int(new_value)))

    def getNodeForResource(self, locator):
        nodes = self.nodes(NodeQuery(tag_locator=TagValue(locator)))
        return nodes[0] if nodes else None
