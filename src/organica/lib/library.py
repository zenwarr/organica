import os, sys, sqlite3, logging, uuid
from organica.utils.lockable import Lockable
import organica.utils.helpers as helpers
from organica.lib.filters import Wildcard, generateSqlCompare, TagFilter, ObjectFilter
from organica.lib.objects import (Object, Tag, TagClass, TagValue, isCorrectIdent,
                                  Identity)
from PyQt4.QtCore import QObject, pyqtSignal
from copy import copy

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
            if exc_type:
                self.lib._rollback()
            else:
                self.lib._commit()
            self.cursor.close()

    _ATTRS_TO_SAVE_ON_TRANSACTION = [
        '_meta', '_tagClasses', '_tags', '_objects'
    ]

    resetted = pyqtSignal() # emitted when library returns to previous state after
                            # rollbacking transaction. In this case it is hard to
                            # determine which changed should be made
    metaChanged = pyqtSignal(object)
    tagClassCreated = pyqtSignal(TagClass)
    tagClassRemoved = pyqtSignal(TagClass)
    tagClassUpdated = pyqtSignal(TagClass, TagClass) # when name or is_hidden changed
    tagCreated = pyqtSignal(Tag)
    tagRemoved = pyqtSignal(Tag)
    tagUpdated = pyqtSignal(Tag, Tag) # when tag value changed
    objectUpdated = pyqtSignal(Object, Object)
    objectCreated = pyqtSignal(Object)
    objectRemoved = pyqtSignal(Object) # when display_name or one of linked tags are changed
                                       # it also emitted when display name can be possible changed
    linkCreated = pyqtSignal(Object, Tag)
    linkRemoved = pyqtSignal(Object, Tag)

    def __init__(self):
        QObject.__init__(self)
        Lockable.__init__(self)
        self._conn = None
        self._filename = ''
        self._meta = {} # map by name
        self._tagClasses = {} # map by name
        self._tags = {} # map by id
        self._objects = {} # map by id
        self._trans_states = []

    @staticmethod
    def loadLibrary(filename):
        if not os.path.exists(filename):
            raise LibraryError('database file {0} does not exists'.format(filename))
        lib = Library()
        lib._connect(filename)

        # check magic row to distinguish organica library
        with self.cursor() as c:
            c.execute("select 1 from organica_meta where name = 'organica' "\
                      + "and value = 'is magic'")
            if not c.fetchone():
                raise LibraryError('database {0} is not organica database'.format(filename))

        # load meta information and tag classes. We always keep all tag classes
        # in memory for quick access
        lib._loadMeta()
        lib._loadTagClasses()
        return lib

    @staticmethod
    def createLibrary(filename):
        # we will not replace existing database
        if os.path.exists(filename):
            raise LibraryError('database file {0} already exists'.format(filename))
        lib = Library()
        lib._connect(filename)

        # create database schema
        # objects id is autoincrement to avoid collating which can occup as we use
        # tags with OBJECT_REFERENCE type.
        # meta and tag class name are not case-sensitive, but object display name is.
        # we are storing some tag class parameters in links table to prevent slow
        # queries to tag classes table.
        with lib.cursor() as c:
            c.executescript("""
                    pragma encoding = 'UTF-8';

                    create table organica_meta(name text collate nocase,
                                               value text);

                    create table objects(id integer primary key autoincrement,
                                         display_name text collate strict_nocase,
                                         obj_flags integer);

                    create table tag_classes(id integer primary key,
                                             name text collate nocase unique,
                                             value_type integer,
                                             hidden integer);

                    create table tags(id integer primary key,
                                      class_id integer,
                                      value_type integer,
                                      value blob,
                                      foreign key(class_id) references tag_classes(id));

                    create table links(object_id integer,
                                       tag_class_id integer,
                                       tag_id integer,
                                       foreign key(object_id) references objects(id),
                                       foreign key(tag_class_id) references tag_classes(id),
                                       unique(object_id, tag_id));
                            """)

            # and add magic meta
            lib.setMeta('organica', 'is magic')
        return lib

    def getMeta(self, meta_name, default = ''):
        # Each meta is pair of strings. Meta name is case-insensitive.
        return self._meta.get(meta_name.casefold(), default)

    def testMeta(self, meta_name):
        # Test meta by absolute name or wildcard.
        if isinstance(meta_name, Wildcard):
            return self._meta.contains(lambda x: meta_name == x)
        else:
            return meta_name.casefold() in self._meta

    def setMeta(self, meta_name, meta_value):
        # writes meta value in database
        meta_name = meta_name.casefold()
        with self.lock:
            if not isCorrectIdent(meta_name):
                raise LibraryError('invalid meta name {0}'.format(meta_name))
            if not isinstance(meta_value, str):
                raise ValueError('meta_value')

            with self.transaction() as c:
                if meta_name in self._meta:
                    if meta_value == self._meta[meta_name]:
                        return
                    c.execute('update organica_meta set value = ? where name = ?',
                              (meta_value, meta_name))
                else:
                    c.execute('insert into organica_meta(name, value) values(?, ?)',
                              (meta_name, meta_value))
                self._meta[meta_name] = meta_value
                self.metaChanged.emit(dict(self._meta))

    def removeMeta(self, meta_name):
        # remove meta with given. Name can be Wildcard
        with self.lock:
            if isinstance(meta_name, Wildcard):
                with self.transaction() as c:
                    c.execute('delete from organica_meta where ' + generateSqlCompare(meta_name))
                    for k in self._meta.keys():
                        if meta_name == k: del self._meta[k]
            elif isinstance(meta_name, str):
                with self.transaction() as c:
                    meta_name = meta_name.casefold()
                    c.execute('delete from organica_meta where name = ?', (meta_name, ))
                    del self._meta[meta_name]
            else:
                raise ValueError('meta_name')
            self.metaChanged.emit(dict(self._meta))

    @property
    def allMeta(self):
        # copy of metas dictionary
        with self.lock:
            return self._meta.copy()

    def _loadMeta(self):
        with self.lock:
            self._meta.clear()
            with self.cursor() as c:
                c.execute("select name, value from organica_meta")
                for r in c.fetchall():
                    if not isCorrectIdent(r[0]):
                        logger.warning('invalid meta name "{0}", ignored'.format(r[0]))
                    else:
                        self._meta[r[0].casefold()] = r[1]

    def _loadTagClasses(self):
        with self.lock:
            with self.transaction() as c:
                c.execute("select id, name, value_type, hidden from tag_classes")
                for r in c.fetchall():
                    tc = TagClass(str(r[1]), int(r[2]), bool(r[3]))
                    if not tc.validate():
                        logger.warn('invalid tag class "{0}" (#{1})'.format(tc.name, r[0]))
                        continue
                    tc.identity = Identity(self, int(r[0]))
                    self._tagClasses[tc.name.casefold()] = tc

    def tagClass(self, tag_class):
        # tag_class can be str, TagClass or Identity
        with self.lock:
            if isinstance(tag_class, Identity) or isinstance(tag_class, TagClass):
                for tclass in self._tagClasses.values():
                    if tclass.identity == tag_class:
                        return copy(tclass)
                else:
                    return None
            else:
                return copy(self._tagClasses.get(tag_class.casefold()))

    def tagClasses(self, name_mask):
        # name_mask: str, Wildcard
        # returns: [TagClass]
        return [copy(x) for x in self._tagClasses.values() if not name_mask or Wildcard(name_mask) == x.name]

    def createTagClass(self, name, value_type = TagValue.TYPE_TEXT, is_hidden = False):
        # name: str
        # value_type: int
        # is_hidden: bool
        # returns: TagClass
        with self.lock:
            tc = TagClass(str(name), int(value_type), bool(is_hidden))

            self._checkTagClass(tc)

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
                          + 'values(?, ?, ?)', (str(name), int(value_type), bool(is_hidden)))
                tc.identity = Identity(self, c.lastrowid)

            # update cached
            self._tagClasses[tc.name.casefold()] = copy(tc)
            self.tagClassCreated.emit(tc)
            return tc

    def removeTagClass(self, tag_class, remove_tags = False):
        # removes given tag class. tag_class can be str, Identity or TagClass
        # also removes tags with this class.
        with self.lock:
            if isinstance(tag_class, str):
                tag_class = self.tagClass(tag_class)

            if not tag_class or not tag_class.isValid or tag_class.lib is not self:
                raise ValueError('tag_class')

            r_class = self.tagClass(tag_class)
            if not r_class:
                raise LibraryError('no tag class #{0} found'.format(tag_class.id))

            # remove tags or ensure there is no them
            if remove_tags:
                self.removeTags(TagFilter().tagClass(tag_class))
            elif self.tags(TagFilter().tagClass(tag_class)):
                raise LibraryError('cannot remove class while there are tags using it')

            with self.transaction() as c:
                c.execute('delete from tag_classes where id = ?', (tag_class.id, ))

            # update cache
            self._tagClasses.remove(r_class.name.casefold())

            # notify
            self.tagClassRemoved.emit(copy(r_class))

    def flushTagClass(self, new_class):
        with self.lock:
            old_class = self.tagClass(new_class.identity)

            if not old_class:
                new_class.identity = self.createTagClass(new_class.name, new_class.valueType,
                                           new_class.hidden).identity
            elif old_class != new_class:
                # update existing one
                self.    TagClass(new_class)

                if new_class.valueType != old_class.valueType:
                    # altering class type is denied because can lead to conversion
                    # errors and unrecoverable data loss
                    raise ValueError('change of tag class value type is impossible')

                names_equal = old_class.name.casefold() == new_class.name.casefold()

                # check if user wants to change class name to already used
                if not names_equal and self.tagClass(new_class.name):
                    raise ValueError('tag class with name {0} already exists'.format(new_class.name))

                with self.transaction() as c:
                    c.execute('update tag_classes set name = ?, is_hidden = ? ' \
                              + 'where id = ?'.format(str(new_class.name),
                                                        bool(new_class.hidden),
                                                        int(new_class.id)))

                # find tags that use this class and change name of class it stores.
                # note that after changing class name existing tag objects will
                # reference not renamed class, but another one (if exists). this
                # can lead to errors.
                affected_tags = self.tags(TagFilter().tagClass(new_class.identity))
                for tag in affected_tags:
                    self._tags[tag.id].tagClassName = new_class.name

                # notify about changes in class and affected tags
                self.tagClassUpdated.emit(copy(new_class))
                for tag in affected_tags:
                    self.tagUpdated.emit(copy(self._tags[tag.id]))

            return new_class

    def getOrCreateTagClass(self, tag_class_name):
        # checks for class with given name. If class exists, return it.
        # Otherwise, new class with default parameters will be created
        # (valueType == TYPE_TEXT, hidden = False)
        with self.lock:
            r_class = self.tagClass(tag_class_name)
            return r_class if r_class else self.createTagClass(tag_class_name)

    @staticmethod
    def _checkTagClass(tag_class):
        # Raise an error if class data is incorrect. It checks if class name is
        # valid identifier and value type is correct.
        if not isCorrectIdent(tag_class.name):
            raise ValueError('invalid tag class name "{0}"'.format(tag_class.name))

        if not TagValue.isValueTypeCorrect(tag_class.valueType):
            raise ValueError('invalid value type for tag class')

    def _tagsFromQuery(self, cursor):
        # Get tags from query executed on cursor assuming that columns are
        # id, class_id, value_type, value
        with self.lock:
            r = []
            for row in cursor.fetchall():
                if row[0] in self._tags:
                    # if we have object in cache, return it
                    r.append(copy(self._tags[row[0]]))
                else:
                    # otherwise create new object and encache it
                    tag_class = self.tagClass(Identity(self, int(row[1])))
                    tag = Tag(tag_class, TagValue.fromDatabaseForm(tag_class, row[3]))
                    if not tag.validate():
                        logger.warn('invalid tag #{0}'.format(row[0]))
                    tag.identity = Identity(self, int(row[0]))
                    self._tags[tag.id] = copy(tag)
                    r.append(tag)
            return r

    def tags(self, query):
        # Query database for tags passing given filters
        if not query: return None

        with self.lock:
            sql = 'select id, class_id, value_type, value from tags where ' \
                     + query.generateSqlWhere()
            with self.cursor() as c:
                c.execute(sql)
                return self._tagsFromQuery(c)

    def tag(self, tag):
        # Get tag with given identity or actual value of given tag
        if not tag or not tag.isValid or tag.lib is not self:
            return None

        if tag.id in self._tags:
            return copy(self._tags[tag.id])
        else:
            r = self.tags(TagFilter().tag(tag))
            return r[0] if r else None

    def createTag(self, tag_class, value):
        # Create new tag with given class and value. Class can be a string, in this
        # case new class with default parameters will be created. If tag_class is of
        # TagClass type, object will be flushed first.
        with self.lock:
            if isinstance(tag_class, str):
                tag_class = self.tagClass(tag_class) or self.createTagClass(tag_class, value.valueType)
            elif isinstance(tag_class, Identity):
                tag_class = self.tagClass(tag_class)
            else:
                tag_class.flush(self)

            tag = Tag(tag_class, value)

            self._checkTag(tag_class, value)

            # check if we already have duplicate of this tag, in this case
            # return value of existing tag
            existing_tags = self.tags(TagFilter().tagClass(tag_class).value(value).limit(1))
            if existing_tags:
                return existing_tags[0]

            with self.transaction() as c:
                c.execute('insert into tags(class_id, value_type, value) ' \
                          'values(?, ?, ?)', (int(tag_class.id),
                                              int(tag_class.valueType),
                                              value.databaseForm()))
                tag.identity = Identity(self, c.lastrowid)

            # encache it
            self._tags[tag.id] = copy(tag)

            # and notify
            self.tagCreated.emit(copy(tag))
            return tag

    def flushTag(self, new_tag):
        with self.lock:
            old_tag = self.tag(new_tag.identity)

            if not old_tag:
                new_tag.identity = self.createTag(new_tag.className, new_tag.value).identity
            else:
                # we deny changing of tag' class because it leads to same problems
                # as changing class' value type
                # as classes can be renamed, we compare not class names, but objects
                if old_tag.tagClass != new_tag.tagClass:
                    raise ValueError('changing class of tag is impossible')

                # all we can change is value
                if old_tag.value != new_tag.value:
                    with self.transaction() as c:
                        c.execute('update tags set value = ? where id = ?' \
                                  .format(tag.value.databaseForm(), new_tag.id))

                    # update cache if tag is encached
                    if new_tag.id in self._tags:
                        self._tags[tag.id].value = new_tag.value

                    # update also objects that depend on this tag. Object.updateTag
                    # method will replace saved tag value with new one, but will not
                    # query database if tags are not fetched. So we cannot determine
                    # which objects depeneds on this tag.
                    for obj in self._objects.values():
                        obj.updateTag(new_tag)

                    # notify about tag
                    self.tagUpdated.emit(copy(old_tag), copy(new_tag))

                    # and about affected objects
                    for obj in self._get_affected_by_tag(new_tag):
                        # objects in set are already copies
                        self.objectUpdated.emit(obj, obj)

            return new_tag

    def removeTag(self, tag, remove_links = False):
        # Remove single tag
        with self.lock:
            if not tag or not tag.isValid or r_tag.lib is not self:
                raise ValueError('tag')

            # get actual value of this tag
            r_tag = self.tag(tag)

            with self.transaction() as c:
                if remove_links:
                    for obj in self.objects(ObjectFilter().tag(TagFilter().tag(r_tag))):
                        self.removeLink(obj, r_tag)
                elif self.objects(ObjectFilter().tag(TagFilter().tag(r_tag))):
                        raise LibraryError('cannot remove tag while there are objects using it')

                c.execute('delete from tags where id = ?', (tag.id, ))

            # update cache
            if tag.id in self._tags: self._tags.remove(tag.id)

            # notify about tag
            self.tagRemoved.emit(copy(r_tag))

            # and affected objects
            for obj in self._get_affected_by_tag(r_tag):
                self.objectUpdated.emit(obj, obj)

    def removeTags(self, tag_filter):
        # Remove all objects which pass the filter
        with self.lock:
            for tag in self.tags(tag_filter): self.removeTag(tag)

    def getOrCreateTag(self, tag_class, tag_value):
        e_tags = self.tags(TagFilter().tagClass(tag_class).value(tag_value))
        return e_tags[0] if e_tags else self.createTag(tag_class, tag_value)

    def createObject(self, display_name_template, tags = None):
        # Create new object with given parameters. Automatically links
        # given tags (flushing them first)
        with self.lock:
            obj = Object(display_name_template)

            with self.transaction() as c:
                c.execute('insert into objects(display_name) values(?)',
                          (str(display_name_template), ))
                obj.identity = Identity(self, c.lastrowid)

                # encache object
                self._objects[obj.id] = copy(obj)

                # link given tags
                if tags:
                    for tag in tags:
                        self.flush(tag)
                        self.createLink(obj, tag)

            self.objectCreated.emit(obj)
            return obj

    def removeObject(self, obj, remove_references = False):
        # Remove object
        with self.lock:
            if not obj or not obj.isValid or obj.lib is not self:
                raise ValueError('obj')

            # get actual value of object
            r_object = self.object(obj)
            if not r_object:
                raise ValueError('no object with id #{0} found'.format(obj.id))

            # remove all links with this object
            for linked_tag in obj.allTags:
                self.removeLink(obj, linked_tag)

            with self.transaction() as c:
                # we should care about tags referencing this object.
                if remove_references:
                    self.removeTags(TagFilter().objectReference(obj))
                elif self.tags(TagFilter().objectReference(obj)):
                        raise LibraryError('cannot remove object while there are references to it')

                c.execute('delete from objects where id = ?', (obj.id, ))

            # update cache
            if obj.id in self._objects: self._objects.remove(obj.id)

            # notify about objects
            self.objectRemoved.emit(copy(r_object))

    def removeObjects(self, obj_filter):
        # remove object that pass given filter
        with self.lock:
            for obj in self.objects(obj_filter): self.removeObject(obj)

    def objectTags(self, obj):
        # Fetch tags that are linked to given object
        # TODO: make filter for it
        if not obj or not obj.isValid or obj.lib is not self:
            raise ValueError('obj')

        with self.cursor() as c:
            c.execute('select id, class_id, value_type, value from tags where id in ' \
                      + '(select tag_id from links where object_id = ?)',
                      (obj.id, ))
            return self._tagsFromQuery(c)

    def objects(self, query):
        # Get object that pass given filter
        if not query: return None

        sql = 'select id, display_name from objects where ' + query.generateSqlWhere()
        with self.cursor() as c:
            c.execute(sql)
            return self._objectsFromQuery(c)

    def object(self, obj):
        # Get object from given Identity or Object
        if obj.id in self._objects:
            return copy(self._objects[obj.id])
        else:
            r = self.objects(ObjectFilter().identity(obj))
            return r[0] if r else None

    def flushObject(self, new_object):
        with self.lock:
            old_object = self.object(new_object)
            if not old_object:
                new_object.identity = self.createObject(new_object.displayNameTemplate,
                                                        new_object.allTags).identity
            else:

                # find links to delete and to create. Flush linked tags.
                tagsToUnlink = []
                tagsToLink = []
                tagsToFlush = []

                for linked_tag in old_object.allTags:
                    if not new_object.testTag(linked_tag.identity):
                        tagsToUnlink.append(linked_tag)
                    else:
                        tagsToFlush.append(linked_tag)

                for tag in new_object.allTags:
                    if not tag.isValid or not old_object.testTag(tag.identity):
                        tagsToLink.append(tag)

                with self.transaction() as c:
                    c.execute('update objects set display_name = ? where id = ?',
                              (new_object.displayNameTemplate, new_object.id))

                    for tag in tagsToUnlink:
                        self.removeLink(new_object, tag)

                    for tag in tagsToLink:
                        self.createLink(new_object, tag)

                    for tag in tagsToFlush:
                        self.flushTag(tag)

                # build actual tag list
                actual_tags = tagsToLink + tagsToFlush
                new_object.setAllTags(actual_tags)

                # update cache
                if new_object.id in self._objects:
                    self._objects[new_object.id] = new_object

                # notify about this object
                self.objectUpdated.emit(copy(old_object), copy(new_object))

                # and affected tags
                affected_objects = self._get_affected(new_object)
                for obj in affected_objects:
                    self.objectUpdated.emit(obj, obj)

            return new_object

    def createLink(self, obj, tag):
        # Create link between object and tag. Silently returns if link
        # already exists.
        if not obj or not obj.isValid or not tag or not tag.isValid or \
                obj.lib is not self or tag.lib is not self:
            raise ValueError()

        with self.lock:
            # get actual values
            unmod_obj, tag = self.object(obj), self.tag(tag)

            # we should check it as object or tag can be deleted to this moment
            if not unmod_obj or not tag or not tag.tagClass:
                raise ValueError()

            if unmod_obj.testTag(tag):
                return # tag already linked: this is not an error

            # we should query for tags to show difference between modified
            # and unmodified object when both these objects will be passed
            # to objectUpdated signal
            unmod_obj.ensureTagsFetched()

            with self.transaction() as c:
                c.execute('insert into links(object_id, tag_class_id, tag_id) ' \
                          + 'values(?, ?, ?)', (unmod_obj.id, tag.tagClass.id, tag.id))

            # update cached object tag list.
            if obj.id in self._objects:
                self._objects[unmod_obj.id].setAllTags(unmod_obj.allTags + [tag])

            actual_obj = self.object(unmod_obj)

            # obj and tag are already copies of cached values
            self.objectUpdated.emit(unmod_obj, actual_obj)

            self.linkCreated.emit(actual_obj, tag)

            for a_obj in self._get_affected(actual_obj):
                self.objectUpdated.emit(a_obj, a_obj)

    def removeLink(self, obj, tag):
        # Removes link between object and tag. Silently returns if no
        # link between them.

        if not obj or not obj.isValid or not tag or not tag.isValid or \
                obj.lib is not self or tag.lib is not self:
            raise ValueError()

        with self.lock:
            unmod_object = self.object(obj)
            unmod_object.ensureTagsFetched()

            if not unmod_object.testTag(TagFilter().identity(tag)):
                return

            with self.transaction() as c:
                c.execute('delete from links where object_id = ? and tag_id = ?',
                          (obj.id, tag.id))

            if obj.id in self._objects:
                actual_tags = [x for x in unmod_object.allTags if x.identity != tag.identity]
                self._objects[obj.id].setAllTags(actual_tags)

            actual_obj = self.object(obj)

            self.objectUpdated.emit(unmod_object, actual_obj)

            self.linkRemoved.emit(actual_obj, self.tag(tag))

            for a_obj in self._get_affected(obj):
                self.objectUpdated.emit(a_obj, a_obj)

    def _objectsFromQuery(self, cursor):
        r = []
        for row in cursor.fetchall():
            if row[0] in self._objects:
                r.append(copy(self._objects[row[0]]))
            else:
                obj = Object(row[1])
                obj.identity = Identity(self, row[0])
                self._objects[obj.id] = obj
                r.append(copy(obj))
        return r

    @staticmethod
    def _checkTag(tag_class, tag_value):
        if tag_class.valueType != tag_value.valueType:
            raise ValueError('type mismatch while trying to set value for tag: ' \
                               'given value is of type {0}, but {1} is expected' \
                               .format(TagValue.typeString(tag_value.valueType),
                                       TagValue.typeString(tag_class.valueType)))

        if not tag_class.name:
            raise ValueError('invalid tag class for tag')

        if tag_value.valueType == TagValue.TYPE_OBJECT_REFERENCE:
            if not self.object(tag_value.objectReference):
                raise ValueError('invalid reference to object with id #{0}' \
                                    .format(tag_value.objectReference))

    def remove(self, lib_object):
        if isinstance(lib_object, TagClass):
            self.removeTagClass(lib_object)
        elif isinstance(lib_object, Tag):
            self.removeTag(lib_object)
        elif isinstance(lib_object, Object):
            self.removeObject(lib_object)
        else:
            raise ValueError()

    def flush(self, lib_object):
        if isinstance(lib_object, TagClass):
            self.flushTagClass(lib_object)
        elif isinstance(lib_object, Tag):
            self.flushTag(lib_object)
        elif isinstance(lib_object, Object):
            self.flushObject(lib_object)
        else:
            raise ValueError()

    @property
    def connection(self):
        with self.lock:
            return self._conn

    def disconnect(self):
        with self.lock:
            if self._conn: self._conn.close()

    @property
    def databaseFilename(self):
        with self.lock:
            return self._filename

    def transaction(self):
        return self.Transaction(self)

    def cursor(self):
        return self.Cursor(self)

    def _begin(self):
        self.lock.acquire() # create additional lock to block other threads
        self._savestate()
        self.connection.execute('savepoint xs')

    def _commit(self):
        assert(self._trans_states)
        self._trans_states.pop()
        self.connection.execute('release xs')
        self.lock.release()

    def _rollback(self):
        assert(self._trans_states)
        self._restorestate()
        self.connection.execute('rollback to xs')
        self.connection.execute('release xs')
        self.lock.release()

    def _savestate(self):
        state = {}
        for attr in self._ATTRS_TO_SAVE_ON_TRANSACTION:
            state[attr] = getattr(self, attr)
        self._trans_states.append(state)

    def _restorestate(self):
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

    def _get_affected(self, obj, watched = None):
        # Get objects that depends on this object.
        r = set()
        # enumerate tags that refers to this object
        for tag in self.tags(TagFilter().objectReference(obj)):
            # enumerate object that have this tag linked
            for obj in self.objects(ObjectFilter().tags(TagFilter().objectReference(obj))):
                # check if object display name can be changed due to changes in tag value
                if obj.displayNameTemplate.dependsOn(tag.className):
                    # prevent looping
                    if not watched or obj not in watched:
                        r.append(copy(obj))
                        r += self._get_affected(obj, r)
        return r

    def _get_affected_by_tag(self, tag):
        # Get objects that are affected by modification or deletion of given tag
        affected_objects = set(self.objects(ObjectFilter().tags(tag)))

        # there are also objects which depends on updated tag in such a way:
        # object display name depends on tag with value type == OBJECT_REFERENCE
        # and which value references object with display name dependent on
        # updated tag value. We use _get_affected to collect these objects.
        appendix = set()
        for obj in affected_objects:
            appendix |= self._get_affected(obj)
        affected_objects |= appendix
        return affected_objects

    def dump(self):
        with self.lock:
            with self.cursor() as c:
                for table in ('organica_meta', 'tag_classes', 'tags', 'objects', 'links'):
                    c.execute('select * from ' + table)

                    print('#### {0}:'.format(table))

                    columns = [x[0] for x in c.description]
                    print('\t'.join(columns))

                    r = c.fetchone()
                    while r:
                        for column in columns:
                            print(r[column], end='\t')
                        print('')
                        r = c.fetchone()

                    print('')
