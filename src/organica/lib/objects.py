import string
from copy import copy, deepcopy

import organica.utils.helpers as helpers


def get_identity(some_object):
    return some_object if isinstance(some_object, Identity) else some_object.identity


def isCorrectIdent(name):
    """Check if name can be used as class or meta name
    """
    return name and isinstance(name, str) and len(name) <= 1000 and \
            helpers.each(name, lambda x: x in string.ascii_letters or x in string.digits or x in '_')


class ObjectError(Exception):
    pass


class Identity(object):
    """Each flushed library object has an identity that unically identifies an entry in
    underlying database. Identity is immutable.
    """
    def __init__(self, lib=None, id=-1):
        self.__lib = lib
        self.__id = id

    @property
    def lib(self):
        return self.__lib

    @property
    def id(self):
        return self.__id

    @property
    def isFlushed(self):
        """Identity is valid (flushed) if there is real database row representing
        corresponding library object.
        """
        return self.lib is not None and self.id > 0

    def __eq__(self, other):
        """Two unflushed identities are not equal"""
        if not isinstance(other, Identity):
            return NotImplemented
        return self.isFlushed and other.isFlushed and self.lib == other.lib and self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

    def __deepcopy__(self, memo):
        # do not deepcopy library reference
        return Identity(self.lib, self.id)


class TagValue(object):
    """Represents value associated with tag.
    Value has a type. Currently only limited set of types is supported:
        - TEXT: textual information mapped to Python str and SQLite TEXT types.
        - NUMBER: integer or floating-point number mapped to Python int or float
                  and SQLite INTEGER or REAL types.
        - LOCATOR: special type representing an URL. Mapped to Python Locator
                  type and SQLite TEXT.
        - NODE_REFERENCE: an identifier of library object. Mapped to node identity in Python
                  and INTEGER referencing row from 'nodes' table in SQLite database.
        - NONE: an empty value. Mapped to Python None and SQLite NULL. Value of
                  this type can be assigned to tags with any value type.
    Note that all types used as values are immutable.
    """

    # constants for value types
    TYPE_NONE, TYPE_TEXT, TYPE_NUMBER, TYPE_LOCATOR, TYPE_NODE_REFERENCE = range(5)

    @staticmethod
    def isValueTypeCorrect(value_type):
        """Check if :value_type: can be used as value type.
        """

        return (TagValue.TYPE_NONE <= value_type <= TagValue.TYPE_NODE_REFERENCE)

    @staticmethod
    def __checkValueTypeCorrect(value_type):
        """Raise exception if :value_type: is not correct
        """

        if not TagValue.isValueTypeCorrect(value_type):
            raise ObjectError('invalid value type: {0}'.format(value_type))

    @staticmethod
    def _type_traits():
        if not hasattr(TagValue, '__type_traits'):
            from organica.lib.locator import Locator

            # function to decode value stored in db to Python object
            def dec_object(tag_class, db_form):
                if tag_class.lib.object(Identity(tag_class.lib, int(db_form))):
                    return Identity(tag_class.lib, int(db_form))
                raise TypeError('invalid id {0} for object reference tag'.format(db_form))

            TagValue.__type_traits = {
                # type_id: (name, prop_name, allowed_python_types, db_encoder, db_decoder)
                TagValue.TYPE_NONE: ('None', '', (type(None), ), None, None),
                TagValue.TYPE_TEXT: ('Text', 'text', (str, ), None, None),
                TagValue.TYPE_NUMBER: ('Number', 'number', (int, float), None, None),
                TagValue.TYPE_LOCATOR: ('Locator', 'locator', (Locator, ), (lambda l: l.databaseForm),
                               (lambda c, d: Locator(d))),
                TagValue.TYPE_NODE_REFERENCE: ('Node reference', 'nodeReference', (Identity, Node),
                                        (lambda obj: obj.id), dec_object)
            }
        return TagValue.__type_traits

    def __init__(self, value=None, value_type=-1):
        if isinstance(value, TagValue):
            self.setValue(value.value, value.valueType)
        else:
            self.setValue(value, value_type)

    def setValue(self, value, value_type=-1):
        """:value_type: = -1 means autodetecting type
        """

        if value_type != -1:
            self.__checkValueTypeCorrect(value_type)
            traits = self._type_traits()[value_type]
            if type(value) not in traits[2]:
                if value is None:
                    # construct default value for this type
                    self.value = traits[2][0]()
                    self.__valueType = value_type
                    return
                else:
                    expected = ' or '.join([x.__name__ for x in traits[2]])
                    raise TypeError('invalid value type for {0} ({1}) - {2} expected'
                            .format(value_type, self.typeString(value_type), expected))

            if value_type != self.TYPE_NONE:
                self.value = value
                self.__valueType = value_type
            else:
                self.setNone()
        else:
            valueType = self.getValueTypeForType(type(value))
            if valueType >= 0:
                self.setValue(value, valueType)
            else:
                raise TypeError('invalid value type for TagValue ({0})'.format(type(value).__name__))

    @property
    def valueType(self):
        return self.__valueType

    def __getattr__(self, name):
        for vt in self._type_traits().keys():
            traits = self._type_traits()[vt]
            if name == traits[1]:
                return self.value if self.valueType == vt else None
        else:
            raise AttributeError()

    def __setattr__(self, name, value):
        for vt in self._type_traits().keys():
            traits = self._type_traits()[vt]
            if name == traits[1]:
                self.setValue(value, vt)
                break
        else:
            return object.__setattr__(self, name, value)

    @property
    def isNone(self):
        return self.valueType == self.TYPE_NONE

    def setNone(self):
        self.__valueType = self.TYPE_NONE
        self.value = None

    @property
    def databaseForm(self):
        """Returns value that can be stored in SQLite database.
        """

        traits = self._type_traits()[self.valueType]
        return traits[3](self.value) if traits[3] else self.value

    def printable(self):
        """Printable (but not precise) form that can be used in
        error messages or something like it (limited in size)
        """

        s = str(self.databaseForm)
        if len(s) > 50:
            s = s[:47] + '...'
        return s

    @staticmethod
    def fromDatabaseForm(cTagClass, dbForm):
        """Returns TagValue object from object stored in database.
        """

        TagValue.__checkValueTypeCorrect(cTagClass.valueType)
        traits = TagValue._type_traits()[cTagClass.valueType]
        dbForm = traits[4](cTagClass, dbForm) if traits[4] else dbForm
        if type(dbForm) not in traits[2]:
            raise TypeError('{0} expected for {1}, got {2}'.format(
                            ' or '.join(traits[2])), traits[0], type(dbForm).__name__)
        return TagValue(dbForm, cTagClass.valueType)

    @staticmethod
    def getValueTypeForType(type_object):
        """Get value type index from Python type
        """

        for vt in TagValue._type_traits().keys():
            traits = TagValue._type_traits()[vt]
            if type_object in traits[2]:
                return vt
        else:
            return -1

    def __eq__(self, other):
        if not isinstance(other, TagValue) and TagValue.getValueTypeForType(type(other)) == -1:
            return NotImplemented

        # try to convert value to TagValue (it means we can compare TagValue and,
        # for example, strings)
        other = TagValue(other)

        if self.valueType != other.valueType or not TagValue.isValueTypeCorrect(self.valueType):
            return False

        # None values are never equal
        if self.valueType == self.TYPE_NONE:
            return False

        # custom comparision for text - should ignore case
        if self.valueType == self.TYPE_TEXT:
            return helpers.cicompare(self.text, other.text)
        else:
            traits = self._type_traits()[self.valueType]
            return getattr(self, traits[1]) == getattr(other, traits[1])

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def typeString(valueType):
        """Human-readable name for value type
        """

        TagValue.__checkValueTypeCorrect(valueType)
        traits = TagValue._type_traits()[valueType]
        return traits[0]

    def __str__(self):
        if self.valueType == self.TYPE_NODE_REFERENCE:
            # do not show user this stuff...
            lib = self.value.lib
            if isinstance(self.value, Identity):
                node = lib.node(self.value)
            return node.displayName
        return str(self.value)

    def convertTo(self, target_type):
        """Converts from one value type to another when it is possible.
        """
        from organica.lib.locator import Locator

        if target_type == self.valueType:
            return TagValue(self)
        elif self.valueType == self.TYPE_NONE:
            return TagValue(None, target_type)

        if target_type == self.TYPE_NONE:
            return TagValue()
        elif target_type == self.TYPE_TEXT:
            return TagValue(str(self), self.TYPE_TEXT)
        elif target_type == self.TYPE_NUMBER:
            if self.valueType == self.TYPE_TEXT:
                try:
                    return TagValue(int(self.text))
                except ValueError as err:
                    return TagValue(0)
            elif self.valueType == self.TYPE_NODE_REFERENCE:
                return TagValue(self.nodeReference.id)
        elif target_type == self.TYPE_LOCATOR:
            return TagValue(Locator(self.text))
        return TagValue(None, target_type)


class LibraryObject(object):
    """Abstract base class for data nodes, tags and tag classes,
    There are some tricks in comparing LibraryObjects. General rule is that
    two library objects are equal if all database-stored properties are
    would be equal after flushing both objects into same library and
    comparing results returned by LibraryObject.flush.
    Speaking of object identity, objects are not equal only if both identities
    are flushed and different. In other cases remained fields will be compared
    to get real result.
    See __eq__ reimplemented method docstrings for details about comparision.
    """

    def __init__(self, identity=None):
        super().__init__()
        self.__identity = identity or Identity()

    @property
    def identity(self):
        return self.__identity

    @identity.setter
    def identity(self, value):
        self.__identity = value

    @property
    def lib(self):
        return self.identity.lib

    @property
    def id(self):
        return self.identity.id

    @property
    def isFlushed(self):
        """True if this object has valid (flushed) identity.
        """

        return self.identity.isFlushed

    def flush(self, lib=None):
        """Flush changes in this object into database. Can modify this object
        identity and (for Node) identites of linked tags.
        """

        if lib:
            if not self.lib:
                self.identity = Identity(lib)
            elif self.lib is not lib:
                raise ObjectError('LibraryObject associated with another library')

        if self.lib:
            self.lib.flush(self)
        else:
            raise ValueError('object cannot be flushed: not associated with any library')


class TagClass(LibraryObject):
    """Tag class is used to describe properties of tags. Classes are immutable.
    You should not instanciate TagClass with constuctor, but instead query
    library for classes.
    """

    def __init__(self, identity, name, value_type, hidden=False):
        super().__init__(identity)

        if not isCorrectIdent(name):
            raise ObjectError('invalid name for tag class: {0}'.format(name))
        if not TagValue.isValueTypeCorrect(value_type):
            raise ObjectError('invalid value type for tag class: {0}'.format(value_type))

        self.__name = name
        self.__valueType = value_type
        self.__hidden = bool(hidden)

    @property
    def name(self):
        return self.__name

    @property
    def valueType(self):
        return self.__valueType

    @property
    def hidden(self):
        return self.__hidden

    def remove(self):
        """If object is flushed, remove it from library
        """

        if self.isFlushed:
            self.lib.remove(self)
            self.identity = Identity(self.lib)

    def __eq__(self, other):
        """Two classes are equal if have same names, value type and hidden flag,
        but never equal if identities are flushed and different. Name comparision
        is not case-sensitive.
        """

        if not isinstance(other, TagClass):
            return NotImplemented

        if self.identity != other.identity and self.isFlushed and other.isFlushed:
            return False

        return helpers.cicompare(self.name, other.name) and \
               self.valueType == other.valueType and \
               self.hidden == other.hidden

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return self.id


class Tag(LibraryObject):
    """Tag is piece of data that can be linked to object. Tag has value and class which defines
    type of value data. You should always construct Tag object with valid (flushed)
    tag class object or its identity (using class name is not allowed).
    If you prefer clean syntax, it is possible to use lib.createTag that accepts
    class name.
    """

    def __init__(self, tag_class=None, tag_value=None):
        super().__init__()
        self.value = TagValue(tag_value)
        if tag_class and not isinstance(tag_class, TagClass):
            raise TypeError('invalid argument: tag_class should be of TagClass type')
        self.tagClass = tag_class

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = TagValue(new_value)

    @property
    def className(self):
        return self.tagClass.name if self.tagClass else ''

    @property
    def valueType(self):
        return self.tagClass.valueType

    def passes(self, condition):
        """Check if this tag satisfies given condition. Condition can be tag Identity - in this case
        method checks if this identity equal to tag identity. Condition can be Tag object - method will
        return result of comparision between :condition: and this tag. Condition can be TagQuery.
        If condition is None, method will return True.
        """

        if condition is None:
            return True
        elif isinstance(condition, Tag):
            return self == condition
        elif isinstance(condition, Identity):
            return self.identity == condition
        else:
            return condition.passes(self)

    def isFriendOf(self, other_tag):
        """Two tags are considered to be friends if there is at least one node that have
        both these tags linked. Tag is always friend of itself.
        """

        if not self.isFlushed or other_tag is None or not other_tag.isFlushed:
            return False

        if self.identity == other_tag.identity:
            return True

        return bool(self.lib.nodes(NodeQuery(linked_with=self) & NodeQuery(linked_with=other_tag)))

    def remove(self, remove_links=False):
        if self.isFlushed:
            self.lib.removeTag(self, remove_links)
            self.identity = Identity(self.lib)

    def __eq__(self, other):
        """Tags are equal if both have same name and value but never equal if identities
        are flushed and different.
        """

        if not isinstance(other, Tag):
            return NotImplemented

        if self.isFlushed and other.isFlushed and self.identity != other.identity:
            return False

        return self.tagClass == other.tagClass and self.value == other.value

    def __ne__(self, other):
        return not self.__eq__(other)


class Node(LibraryObject):
    """Node represents object in database. It has display name generated dynamically basing on
    display name template and set of linked tags.
    """

    def __init__(self, display_name='', tags=None):
        super().__init__()
        self.displayNameTemplate = display_name
        self.__allTags = []
        self.__tagsFetched = False
        if tags:
            for tag in tags:
                self.linkTag(tag)

    @property
    def displayName(self):
        from organica.lib.formatstring import FormatString
        return FormatString(self.displayNameTemplate).format(self)

    @property
    def allTags(self):
        """Get deep copy of list containing all tags linked with this node.
        """

        self.ensureTagsFetched()
        return deepcopy(self.__allTags)

    @allTags.setter
    def allTags(self, new_tags):
        self.setAllTags(new_tags)

    def setAllTags(self, value):
        """Overrides list containing tags linked with given value. Value should be list of Tag objects.
        """

        self.__tagsFetched = True
        self.__allTags = deepcopy(value)

    def tags(self, condition=None):
        """Get list of tags that satisfies given condition. See Tag.passes for details about condition.
        """

        self.ensureTagsFetched()
        return [deepcopy(t) for t in self.__allTags if t.passes(condition)]

    def testTag(self, condition):
        """Check if at least one tag satisfying given condition is linked with node. See Tag.passes for
        details about condition.
        """

        self.ensureTagsFetched()
        return any((t.passes(condition) for t in self.__allTags))

    def passes(self, condition):
        """Check if this node satisfies given condition. Condition can be node Identity - in this case
        method checks if this identity equal to node identity. Condition can be Node - method will
        return result of comparision between :condition: and this node. Condition can be NodeQuery.
        If condition is None, method will return True.
        """

        if condition is None:
            return True
        elif isinstance(condition, Identity):
            return self.identity == condition
        elif isinstance(condition, Node):
            return self == condition
        else:
            return condition.passes(self)

    @staticmethod
    def commonTags(nodeList):
        """Get list of tags that are linked to all nodes in list. Tags are compared by standard method (__eq__)
        """

        if not nodeList:
            return []

        result = nodeList[0].allTags
        for node in nodeList[1:]:
            result = [tag for tag in result if node.testTag(tag)]
        return result

    def linkTag(self, tag):
        """Link tag to this node. If same tag already linked to node, ObjectError will be raised.
        Note that even tags with non-equal identities but having equal classes and values will conflict.
        Node will hold copy of given Tag object, not original one.
        """

        from organica.lib.filters import TagQuery
        if self.testTag(TagQuery(tag_class=tag.tagClass, value=tag.value)):
            raise ObjectError('tag {0}:{1} already linked to object'.format(tag.className, tag.value.printable()))
        else:
            self.__allTags.append(deepcopy(tag))

    def linkNewTag(self, tag_class, tag_value):
        """Convenience method that creates tag with given class and value and immediately links it
        to this node. Created tag is not flushed.
        """

        self.linkTag(Tag(tag_class, tag_value))

    def link(self, *args):
        """Convenience method accepting one or two arguments. In first case it acts just like
        Node.linkTag method, in second case - just like Node.linkNewTag method.
        """

        if len(args) == 1:
            self.linkTag(args[0])
        elif len(args) == 2:
            self.linkNewTag(args[0], args[1])
        else:
            raise TypeError('Node.link() takes 1 or 2 arguments, but {0} given'.format(len(args)))

    def unlink(self, condition):
        """Unlink tag linked to node. Can accept following argument of types:
            - Identity: removes tag with this identity. If invalid identity given,
                        ObjectError is raised. If no tag with given identity is linked,
                        ObjectError is raised.
            - Tag: removes tag which equal to given one. If no such tag linked, ObjectError
                        is raised.
            - TagQuery: removes tags that pass given query. Does not raise ObjectError
                        when no tags found.
        """

        self.ensureTagsFetched()

        if isinstance(condition, (Identity, Tag)):
            if not self.testTag(condition):
                if isinstance(condition, Identity):
                    m = '#{0}'.format(condition.id)
                else:
                    m = '{0}:{1} (#{2})'.format(condition.className, condition.value.printable(),
                                                condition.id)
                raise ObjectError('tag {0} is not linked to node'.format(m))
            self.__allTags = [x for x in self.__allTags if not x.passes(condition)]
        else:
            self.__allTags = [x for x in self.__allTags if not condition.passes(x)]

    def __eq__(self, other):
        """Nodes are different from other LibraryObject.
        Nodes can be equal only if both identities ARE FLUSHED
        and equal, and displayNameTemplates and allTags are equal too.
        So two copy of same unflushed node will not be equal.
        """

        if not isinstance(other, Node):
            return NotImplemented

        if self.identity != other.identity:
            return False

        self.ensureTagsFetched()
        return self.displayNameTemplate == other.displayNameTemplate and \
               len(Node.commonTags((self, other))) == len(self.__allTags)

    def __ne__(self, other):
        return not self.__eq__(other)

    def ensureTagsFetched(self):
        """When node is initialized from database, code will not automatically query for linked tags
        at the moment (for perfomance). This is made in call to this method. Method is automatically
        invoked by class code when necessary (but it can be helpful under some conditions to use this
        method manually). Tags are not fetched from database twice.
        """

        if self.isFlushed and not self.__tagsFetched:
            self.__allTags = self.lib.nodeTags(self)
        self.__tagsFetched = True

    def updateTag(self, tag):
        """This method is used internally by Library object code to update linked tag when it is updated.
        """

        if self.isFlushed and self.__tagsFetched:
            for i in range(len(self.__allTags)):
                if self.__allTags[i].isFlushed and self.__allTags[i].identity == tag.identity:
                    self.__allTags[i] = deepcopy(tag)
                    break

    def remove(self, remove_references=False):
        if self.isFlushed:
            self.lib.removeNode(self, remove_references)
            self.identity = Identity(self.lib)
