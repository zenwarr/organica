from organica.lib.locator import Locator
from organica.lib.formatstring import FormatString
import organica.lib.filters
import organica.utils.helpers as helpers

def isCorrectIdent(name):
    """
    Checks if name can be used as tag class or meta name
    """
    return helpers.each(name, lambda x: x.isalnum() or x in '_')

class ObjectError(Exception):
    pass

class Identity(object):
    """
    Each flushed library object has an identity that unically identifies an entry in
    underlying database and helps distinguish it from other objects.
    Identity is immutable.
    """
    def __init__(self, lib = None, id = -1):
        self.__lib = lib
        self.__id = id

    @property
    def lib(self):
        return self.__lib

    @property
    def id(self):
        return self.__id

    @property
    def isValid(self):
        """
        Identity is valid if there is real database row representing corresponding
        library object.
        """
        return self.lib and self.id > 0

    def __eq__(self, other):
        if not isinstance(other, Identity):
            return NotImplemented
        return self.isValid and other.isValid and self.lib == other.lib \
                and self.id == other.id

    def __ne__(self, other):
        return not self.__eq__(other)

class TagValue(object):
    """
    Represents value linked with tag.
    Value has a type. Currently only limited set of types is supported:
        - TEXT: textual information mapped to Python str or SQLite TEXT types.
        - NUMBER: integer or floating-point number mapped to Python int or float
                  or SQLite integer or real types.
        - LOCATOR: special type representing an URL. Mapped to Python Locator
                  type. Represented with TEXT in SQLite.
        - OBJECT_REFERENCE: an identifier of library object. Mapped to Object in Python
                  and integer referencing table objects in SQLite database.
        - NONE: an invalid value. Mapped to Python None and SQLite NULL. This type
                is compatible with all other types and value of this type can be
                assigned to tag with any type.
    """

    # values for supported types
    TYPE_NONE = 0
    TYPE_TEXT = 1
    TYPE_NUMBER = 2
    TYPE_LOCATOR = 3
    TYPE_OBJECT_REFERENCE = 4

    @staticmethod
    def _dec_object(tag_class, db_form):
        if tag_class.lib.object(Identity(tag_class.lib, int(db_form))):
            return Identity(tag_class.lib, int(db_form))
        raise TypeError('invalid id {0} for object reference tag'.format(db_form))

    @staticmethod
    def isValueTypeCorrect(value_type):
        """
        Check if :value_type: can be used as type index. This check should be made
        after index was get from user or database
        """
        return (0 <= value_type <= TagValue.TYPE_OBJECT_REFERENCE)

    @staticmethod
    def _checkValueTypeCorrect(value_type):
        """
        Raise exception if :value_type: is not correct
        """
        if not TagValue.isValueTypeCorrect(value_type):
            raise ObjectError('invalid value type index')

    _type_traits = {
        # type_id: (name, prop_name, allowed_python_types, db_encoder, db_decoder)
        TYPE_NONE: ('None', '', ('NoneType', ), None, None),
        TYPE_TEXT: ('Text', 'text', ('str', ), None, None),
        TYPE_NUMBER: ('Number', 'number', ('int', 'float'), None, None),
        TYPE_LOCATOR: ('Locator', 'locator', (type(Locator).__name__, ), (lambda l: l.databaseForm()),
                       (lambda c, d: Locator(d))),
        TYPE_OBJECT_REFERENCE: ('Object reference', 'objectReference', (type(Identity).__name__, ),
                                (lambda obj: obj.id), _dec_object)
    }

    def __init__(self, value = None, value_type = -1):
        if isinstance(value, TagValue):
            self.setValue(value.value, value.valueType)
        else:
            self.setValue(value, value_type)

    def setValue(self, value, value_type = -1):
        """
        :value_type: = -1 means autodetecting type
        """
        if value_type != -1:
            self._checkValueTypeCorrect(value_type)
            traits = self._type_traits[value_type]
            if type(value).__name__ not in traits[2]:
                expected = ' or '.join(traits[2])
                raise TypeError('invalid value type for {0} ({1}) - {2} expected'
                        .format(value_type, self.typeString(value_type), expected))

            if value_type != self.TYPE_NONE:
                self.value = value
                self.valueType = value_type
            else:
                self.setNone()
        else:
            valueType = self.getValueTypeForType(type(value))
            if valueType >= 0:
                self.setValue(value, valueType)
            else:
                raise TypeError('invalid value type for TagValue ({0})'.format(type(value).__name__))

    def __getattr__(self, name):
        if not name: raise AttributeError()

        for vt in self._type_traits.keys():
            traits = self._type_traits[vt]
            if name == traits[1]:
                return self.value if self.valueType == vt else None
        else:
            raise AttributeError()

    def __setattr__(self, name, value):
        if not name: raise AttributeError()

        for vt in self._type_traits.keys():
            traits = self._type_traits[vt]
            if name == traits[1]:
                self.setValue(value, vt)
        else:
            return object.__setattr__(self, name, value)

    @property
    def isNone(self):
        return self.valueType == self.TYPE_NONE

    def setNone(self):
        self.valueType = self.TYPE_NONE
        self.value = None

    def databaseForm(self):
        """
        Returns value that can be stored in SQLite database.
        """
        self._checkValueTypeCorrect(self.valueType)
        traits = self._type_traits[self.valueType]
        return traits[3](self.value) if traits[3] else self.value

    def printable(self):
        """
        Printable (but not precise) form that can be used in error messages or something like it
        """
        s = str(self.databaseForm())
        if len(s) > 50:
            s = s[:47] + '...'
        return s

    @staticmethod
    def fromDatabaseForm(cTagClass, dbForm):
        """
        Returns TagValue object from object stored in database.
        """
        self._checkValueTypeCorrect(cTagClass.valueType)
        traits = self._type_traits[cTagClass.valueType]
        dbForm = traits[4](cTagClass, dbForm) if traits[4] else dbForm
        if type(dbForm).__name__ not in traits[2]:
            raise TypeError('{0} expected for {1}, got {2}'.format(
                            ' or '.join(traits[2])), traits[0], type(dbForm).__name__)
        return TagValue(dbForm, cTagClass.valueType)

    @staticmethod
    def getValueTypeForType(type_object):
        """
        Get value type index from Python type
        """
        for vt in TagValue._type_traits.keys():
            traits = TagValue._type_traits[vt]
            if type_object.__name__ in traits[2]:
                return vt
        else:
            return -1

    def __eq__(self, other):
        if not isinstance(other, TagValue) or TagValue.getValueTypeForType(type(other)) == -1:
            return NotImplemented

        # try to convert value to TagValue (it means we can compare TagValue and, for example, strings)
        other = TagValue(other)

        if self.valueType != other.valueType or not TagValue.isValueTypeCorrect(self.valueType):
            return False

        # None values are never equal
        if self.valueType == self.TYPE_NONE: return False

        traits = self._type_traits[self.valueType]
        return getattr(self, traits[1]) == getattr(other, traits[1])

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def typeString(valueType):
        """
        Human-readable name for value type
        """
        self._checkValueTypeCorrect(valueType)
        traits = TagValue._type_traits[valueType]
        return traits[0]

class LibraryObject(object):
    def __init__(self, identity = None):
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
    def isValid(self):
        return self.identity.isValid

    def validate(self):
        return True

class TagClass(LibraryObject):
    def __init__(self, name = '', value_type = TagValue.TYPE_TEXT, hidden = False):
        super().__init__()
        self.name = name
        self.valueType = value_type
        self.hidden = hidden

    def flush(self):
        if self.lib: self.lib.flush(self)

    def remove(self):
        if self.lib: self.lib.remove(self)

    def __m_eq(self, other):
        return self.name.casefold() == other.name.casefold() and \
                self.hidden == other.hidden and self.valueType == other.valueType

    def __eq__(self, other):
        if not isinstance(other, TagClass): return NotImplemented

        if not self.isValid and not other.isValid:
            return self.__m_eq(other)
        else:
            return self.__m_eq(other) and self.identity == other.identity

    def __ne__(self, other):
        return not self.__eq__(other)

    def validate(self):
        return isCorrectIdent(self.name) and (0 <= self.valueType < TagValue.TYPE_MAXIMAL)

class Tag(LibraryObject):
    """
    Tag is named piece of data that can be linked to object. Tag has class which defines
    type of data.
    There is some trick with tag class and tag class name. To allow creating tag object in this way:
        tag = Tag('class_name', TagValue(TagValue.TYPE_TEXT, 'class_value'))
    we cannot always query library for class with name 'tag_class'. We can create tag object at time
    when this class is not created or library itself does not exists. Because of this we can store only
    class name, but not TagClass object itself. But when code requests TagClass with call to property
    Tag.tagClass we query library to get actual object.
    When flushing tag, code will check if class with name specified exists. If does, this class will be
    assigned to tag and value is checked for type mismatch. Otherwise new class is created with
    type == Tag.value type and other parameters set by default. This scheme can cause some problems
    - at example, when we have two tags having values of different types and same class name,
    it is undefined which type will created class have. It depends on which tag is flushed first.
    """
    def __init__(self, tag_class = None, tag_value = None):
        super().__init__()
        self.value = tag_value if tag_value else TagValue()

        if isinstance(tag_class, TagClass):
            self.className = tag_class.name
        elif isinstance(tag_class, Identity):
            tc = tag_class.lib.tagClass(tag_class)
            self.className = tc.name if tc else ''
        else:
            self.className = tag_class

    @property
    def tagClass(self):
        return self.lib.tagClass(self.className) if self.lib else None

    @tagClass.setter
    def tagClass(self, tag_class):
        self.className = tag_class.name if isinstance(tag_class, TagClass) else tag_class

    def passes(self, tag_filter):
        if not tag_filter:
            return self.isValid
        elif isinstance(tag_filter, Tag) or isinstance(tag_filter, Identity):
            tag_filter = filters.TagFilter().tag(tag_filter)
        return tag_filter.passes(self)

    def __m_eq(self, other):
        return self.className == other.className and self.value == other.value

    def __eq__(self, other):
        if not isinstance(other, Tag): return NotImplemented

        if not self.isValid and not other.isValid:
            return self.__m_eq(other)
        else:
            return self.__m_eq(other) and self.identity == other.identity

    def __ne__(self, other):
        return not self.__eq__(other)

    def flush(self):
        if self.lib: self.lib.flush(self)

    def remove(self):
        if self.lib: self.lib.remove(self)

    def validate(self):
        return isCorrectIdent(self.className) and \
                (0 <= self.value.valueType < TagValue.TYPE_MAXIMAL)

class Object(LibraryObject):
    def __init__(self, display_name = '', tags = None):
        super().__init__()
        self.displayNameTemplate = display_name
        self.__allTags = []
        self.__tagsFetched = False
        if tags:
            for name, value in tags:
                self.linkTag(Tag(name, value))

    @property
    def displayName(self):
        return FormatString(self.displayNameTemplate).format(self)

    @property
    def allTags(self):
        self.ensureTagsFetched()
        return self.__allTags

    def setAllTags(self, value):
        self.__tagsFetched = True
        self.__allTags = value

    def tags(self, tag_filter = None):
        self.ensureTagsFetched()
        return [t for t in self.__allTags if t.passes(tag_filter)]

    def testTag(self, tag_filter):
        self.ensureTagsFetched
        return contains(self.__allTags, lambda t: not t.passes(tag_filter))

    def passes(self, obj_filter):
        if obj_filter is None:
            return self.isValid
        elif isinstance(obj_filter, Object):
            obj_filter = ObjectFilter.object(obj_filter)
        elif isinstance(obj_filter, Identity):
            obj_filter = ObjectFilter.objectIdentity(obj_filter)
        return obj_filter.passes(self)

    @staticmethod
    def commonTags(objectList):
        if len(objectList) == 0:
            return []
        elif len(objectList) == 1:
            return objectList[0].allTags

        def check_t(tag, object):
            return object.testTag(TagFilter().tagClass(tag.tagClass.name).value(tag.value))

        result = objectList[0].allTags
        for obj in objectList[1:]:
            result = [t for t in result if check_t(t, obj)]
        return result

    def linkTag(self, tag):
        if not self.testTag(TagFilter().tagClass(tag.tagClass).value(tag.value)):
            self.__allTags.append(tag)
        else:
            raise ObjectError('tag {0}:{1} already linked to object'.format(tag.name, tag.value.printable()))

    def linkNewTag(self, tag_class, tag_value):
        self.linkTag(Tag(tag_class, tag_value))

    def link(self, *args):
        if len(args) == 1:
            self.linkTag(args[0])
        elif len(args) == 2:
            self.linkNewTag(args[0], args[1])
        else:
            raise TypeError('Object.link() takes 1 or 2 arguments, but {0} given'.format(len(args)))

    def unlink(self, tag_filter):
        self.ensureTagsFetched()
        if tag not in self.__allTags:
            raise ObjectError('tag is not linked')
        self.__allTags.remove(tag)

    def remove(self):
        if self.isValid(): self.lib.remove(self)

    def flush(self):
        if self.isValid(): self.lib.flush(self)

    def __m_eq(self, other):
        return self.displayNameTemplate == other.displayNameTemplate \
                and self.allTags == other.allTags

    def __eq__(self, other):
        if not isinstance(other, Object): return NotImplemented

        if not self.isValid and not other.isValid:
            return self.__m_eq(other)
        else:
            return self.__m_eq(other) and self.identity == other.identity

    def __ne__(self, other):
        return not self.__eq__(other)

    def ensureTagsFetched(self):
        if self.isValid and not self.__tagsFetched:
            self.allTags = self.lib.objectTags(self)
        self.__tagsFetched = True

    def updateTag(self, tag):
        if self.__tagsFetched:
            for i in range(len(self.__allTags)):
                if self.__allTags[i].identity == tag.identity:
                    self.__allTags[i] = tag
                    break
