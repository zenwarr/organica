from organica.lib.locator import Locator
from organica.lib.formatstring import FormatString

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
        - OBJECT REFERENCE: an identifier of library object. Mapped to Object in Python
                  and foreign key referencing table objects in SQLite database.
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

    def __init__(self, value, value_type = -1):
        self.setValue(value, value_type)

    def setValue(self, value, value_type = -1):
    	"""
    	value_type = -1 means autodetecting type
    	"""
        if value_type == self.TYPE_NONE:
            if value:
                raise TypeError('invalid value for TagValue: None expected')
            self.value = None
        elif value_type == self.TYPE_TEXT:
            if not isinstance(value, str):
                raise TypeError('invalid value for TagValue: str expected')
            self.value = value
        elif value_type == self.TYPE_NUMBER:
            if not isinstance(value, int) and not isinstance(value, float):
                raise TypeError('invalid value for TagValue: int or float expected')
            self.value = value
        elif value_type == self.TYPE_LOCATOR):
            if not isinstance(value, Locator) and not isinstance(value, str):
                raise TypeError('invalid value for TagValue: Locator or str expected')
            if isinstance(value, str):
                self.value = Locator(value)
            else:
                self.value = value
        elif value_type == self.TYPE_OBJECT_REFERENCE:
            if not isinstance(value, Object):
                raise TypeError('invalid value for TagValue: Object expected')
            self.value = value
        elif value_type == -1:
            # autodetect type
            type_map = {
                type(str): self.TYPE_TEXT,
                type(int): self.TYPE_NUMBER,
                type(float): self.TYPE_NUMBER,
                type(Locator): self.TYPE_LOCATOR:
                type(Object): self.TYPE_OBJECT_REFERENCE:
                type(None): self.TYPE_NONE
            }
            if type(value) not in type_map:
                raise TypeError('invalid value for TagValue')
            else:
                self.setValue(value, type_map[type(value)])
        else:
            raise TypeError('invalid value type for TagValue')

    @property
    def text(self):
        return self.value if self.valueType == TYPE_TEXT else None

    @text.setter
    def setText(self, value):
        self.setValue(value, self.TYPE_TEXT)

    @property
    def number(self):
        return self.value if self.valueType == TYPE_NUMBER else None

    @number.setter
    def setNumber(self, value):
        self.setValue(value, self.TYPE_NUMBER)

    @property
    def objectReference(self):
        return self.value if self.valueType == TYPE_OBJECT_REFERENCE else None

    @objectReference.setter
    def setObjectReference(self, value):
        self.setValue(value, self.TYPE_OBJECT_REFERENCE)

    @property
    def locator(self):
        return self.value if self.valueType == TYPE_LOCATOR else None

    @locator.setter
    def setLocator(self, value):
        self.setValue(value, self.TYPE_LOCATOR)

    @property
    def isNone(self):
        return self.valueType == TYPE_NONE

    def setNone(self):
    	self.valueType = TYPE_NONE
    	self.value = None

    def databaseForm(self):
        """
        Returns value that can be stored in SQLite database.
        """
        if self.valueType == self.TYPE_TEXT or self.valueType == self.TYPE_NUMBER:
            return self.value
        elif self.valueType == self.TYPE_LOCATOR:
            return self.value.url()
        elif self.valueType == self.TYPE_OBJECT_REFERENCE:
            return '#{0}'.format(self.value.id)
        else:
            return None

    def printable(self):
    	s = str(self.databaseForm())
    	if len(s) > 50:
    		s = s[:47] + '...'
    	return s

    @staticmethod
    def fromDatabaseForm(cTagClass, dbForm):
        """
        Returns TagValue object from object stored in database.
        """
        result = TagValue()
        if cTagClass.valueType == self.TYPE_TEXT:
            # database form should be text
            if not isinstance(str, dbForm):
                raise TypeError('string expected for text tag')
            else:
                result.text = dbForm
        elif cTagClass.valueType == self.TYPE_NUMBER:
            if not isinstance(int, dbForm) and not isinstance(float, dbForm):
                raise TypeError('number expected for number tag')
            else:
                result.number = dbForm
        elif cTagClass.valueType == self.TYPE_OBJECT_REFERENCE:
            if not isinstance(str, dbForm):
                raise TypeError('string expected for object reference')
            elif not dbForm.startswith('#'):
                raise TypeError('bad format for object reference')
            else:
                objectId = int(val[1:])
                libObject = cTagClass.lib.object(objectId)
                if libObject is None:
                    raise TypeError('invalid id #{0} for TYPE_OBJECT_REFERENCE tag' \
                                .format(objectId))
                else:
                    result.objectReference = libObject
        elif cTagClass.valueType == TYPE_LOCATOR:
            if not isinstance(str, dbForm):
                raise TypeError('string expected for locator')
            result.locator = Locator(dbForm)
        elif cTagClass.valueType == self.TYPE_NONE:
        	result.setNone()
        else:
            raise TypeError('unknown type for tag class {1}'.format(cTagClass.name))
        return result

    def __eq__(self, other):
        if self.typeIndex != other.typeIndex:
            return False

        if self.typeIndex == self.TYPE_TEXT:
            return self.text == other.text
        elif self.typeIndex == self.TYPE_NUMBER:
            return self.number == other.number
        elif self.typeIndex == self.TYPE_OBJECT_REFERENCE:
            return self.objectReference == other.objectReference
        elif self.typeIndex == self.TYPE_LOCATOR:
            return self.locator == other.locator
        else:
            # NONE type values are never equal
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def typeString(typeIndex):
        typeMap = {TagValue.TYPE_NONE: 'None',
                   TagValue.TYPE_TEXT: 'Text',
                   TagValue.TYPE_NUMBER: 'Number',
                   TagValue.TYPE_OBJECT_REFERENCE: 'Object reference',
                   TagValue.TYPE_LOCATOR: 'Locator'}
        return typeMap[typeIndex] if typeMap.contains(typeIndex) else 'Unknown'

class LibraryObject(object):
    def __init__(self, identity = None):
        super().__init__()
        self.__identity = identity if identity else Identity()

    @property
    def identity(self):
        return self.__identity

    @identity.setter
    def setIdentity(self, value):
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

class TagClass(LibraryObject):
    def __init__(self, name = '', value_type = TagValue.TYPE_TEXT, hidden = False):
        super().__init__()
        self.name = name
        self.valueType = valueType
        self.hidden = hidden

    def flush(self):
        if self.lib: self.lib.flush(self)

    def remove(self):
        if self.lib: self.lib.remove(self)

    def __m_eq(self, other):
        return self.name.casefold() == other.name.casefold() and \
                self.hidden == other.hidden and self.valueType == other.valueType

    def __eq__(self, other):
        if not self.isValid and not other.isValid:
            return self.__m_eq(other)
        else:
            return self.__m_eq(other) and self.identity == other.identity

    def __ne__(self, other):
        return not self.__eq__(other)

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
        self.tagClass = tag_class

    @property
    def tagClass(self):
        return self.lib.tagClass(self.className) if self.lib else None

    @tagClass.setter
    def setTagClass(self, tag_class):
        self.className = tag_class.name if isinstance(tag_class, TagClass) else tag_class

    def passes(self, tag_filter):
    	if not tag_filter:
    		return self.isValid
    	elif isinstance(tag_filter, Tag):
    		tag_filter = TagFilter.tag(tag_filter)
    	elif isinstance(tag_filter, Identity):
    		tag_filter = TagFilter.tagIdentity(tag_filter)
    	return tag_filter.passes(self)

    def __m_eq(self, other):
    	return self.className == other.className and self.value == other.value

    def __eq__(self, other):
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
        return FormatString(self.displayNameTemplate).format(self, FormatString.FCONTEXT_DISPLAY_NAME)

    @property
    def allTags(self):
        self.__ensureTagsFetched()
        return self.__allTags

    @allTags.setter
    def setAllTags(self, value):
        self.__tagsFetched = True
        self.__allTags = value

    def tags(self, tag_filter = None):
        self.__ensureTagsFetched()
        return [t for t in self.__allTags if t.passes(tag_filter)]

    def testTag(self, tag_filter):
        self.__ensureTagsFetched
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
            return object.testTag( \
                    TagFilter.whereClass(tag.tagClass.name) and \
                    TagFilter.whereValue(tag.value))

        result = objectList[0].allTags
        for obj in objectList[1:]:
            result = [t for t in result if check_t(t, obj)]
        return result

    def linkTag(self, tag):
    	if not self.testTag(TagFilter.tagClass(tag.tagClass) and \
    	                    TagFilter.value(tag.value)):
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
        self.__ensureTagsFetched()
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
        if not self.isValid and not other.isValid:
            return self.__m_eq(other)
        else:
            return self.__m_eq(other) and self.identity == other.identity

    def __ne__(self, other):
        return not self.__eq__(other)

    def __ensureTagsFetched(self):
        if self.isValid and not self.__tagsFetched:
            self.allTags = self.lib.objectTags(self)
        self.__tagsFetched = True
