import re, operator, copy
from organica.lib.objects import Object, Tag, TagClass, TagValue, Identity, get_identity
import organica.utils.helpers as helpers

class Wildcard(object):
    def __init__(self, pattern = ''):
        self.pattern = pattern if not isinstance(pattern, Wildcard) else pattern.pattern

    def isEqual(self, text):
        # empty pattern matches empty string
        if not self.pattern: return not text

        if not text: return False

        # generate regular expression we can use
        # escape all regexp special chars except supported * and ?
        pattern_re = helpers.escape(self.pattern, '[\\^$.|+()') + '$'
        # and translate wildcard special chars to regexp
        pattern_re = pattern_re.replace('*', '.*').replace('?', '.?')
        return bool(re.compile(pattern_re, re.IGNORECASE).match(text))

    def __eq__(self, text):
        # comparing with ordinary str will cause matching wildcard;
        # comparing with another wildcard will cause comparing patterns.
        # note that it compares patterns as strings, but two patterns can
        # have same meaning but different representations.
        if isinstance(text, Wildcard):
            return self.pattern.casefold() == text.pattern.casefold()
        elif isinstance(text, str):
            return self.isEqual(text)
        else:
            return NotImplemented

    def __ne__(self, text):
        return not self.__eq__(text)

def _sqlEqualForm(text):
    """
    Doubles each single quote. Use it to sanitize strings which will be passed
    into query in constucts like this: row = 'some_text'
    """
    r = ''
    for x in text:
        r = r + (x if x != "\'" else "''")
    return r

def _sqlLikeForm(text):
    """
    Escapes string for use with LIKE ? ESCAPE '!'.
    Standard escape sequences are not recognized, except \* \? and \\
    """
    result = ''
    escaping = False
    for c in text:
        if escaping:
            if c not in ('*', '?', '\\'):
                result += '\\'
            result += c
            escaping = False
        else:
            trans_chars = {
                '*': '%',
                '?': '_',
                '_': '!_',
                '%': '!%',
                '!': '!!',
                "\'": "''"
            }
            if c == '\\':
                escaping = True
            elif c in trans_chars:
                result += trans_chars[c]
            else:
                result += c

    if escaping:
        # escape slash at end of string, warn
        # log("escape slash at end of string: {0}".format(self.__text), LOG_WARNING)
        result += '\\'

    return result

def generateSqlCompare(row_name, template):
    """
    Generate sql equal or LIKE comparision depending on type of template.
    If template is None, comparision will be TRUE only on empty strings or NULLs.
    """
    if not template:
        return "{0} = '' or {0} is null".format(row_name)
    elif isinstance(template, Wildcard):
        return "{0} like '{1}' escape '!'".format(row_name, _sqlLikeForm(template.pattern))
    else:
        return "{0} = '{1}'".format(row_name, _sqlEqualForm(template))

class _Filter_Disabled(object):
    """
    Disabled filter passes all tags.
    """
    def isPasses(self, tag):
        return bool(tag)

    def generateSql(self):
        return '1 = 1'

class _Filter_Block(object):
    """
    Blocked filter passes no tags
    """
    def isPasses(self, obj):
        return False

    def generateSql(self):
        return '1 = 2'

class _Filter_And(object):
    """
    This filter is TRUE only when :left: and :right: filters are TRUE. If one
    of these filters is None, it considered to be disabled (always TRUE).
    """
    def __init__(self, left, right):
        self.__left = left
        self.__right = right

    def isPasses(self, obj):
        if not obj: return False

        if self.__left and not self.__left.isPasses(obj):
            return False
        if self.__right and not self.__right.isPasses(obj):
            return False
        return True

    def generateSql(self):
        if self.__left and self.__right:
            return '({0}) and ({1})'.format(self.__left.generateSql(),
                                              self.__right.generateSql())
        elif not self.__left and not self.__right:
            return _Filter_Disabled().generateSql()
        else:
            return (self.__left if self.__left else self.__right).generateSql()

class _Filter_Or(object):
    """
    This filter is TRUE if at least one of :left: and :right: filters is TRUE.
    If one of these filters is None, it considered to be TRUE
    """
    def __init__(self, left, right):
        self.__left = left
        self.__right = right

    def isPasses(self, obj):
        if not self.__left or self.__left.isPasses(obj):
            return True
        if not self.__right or self.__right.isPasses(obj):
            return True
        return False

    def generateSql(self):
        if self.__left and self.__right:
            return '({0}) or ({1})'.format(self.__left.generateSql(),
                                             self.__right.generateSql())
        else:
            return _Filter_Disabled().generateSql()

class _Filter_Not(object):
    """
    Inverts value of another filter. If constucted with None filter, returns False
    """
    def __init__(self, expr):
        self.__expr = expr

    def isPasses(self, obj):
        return self.__expr and not self.__expr.isPasses(obj)

    def generateSql(self):
        if not self.__expr:
            return _Filter_Block().generateSql()
        return 'not ({0})'.format(self.__expr.generateSql())

class _Filter(object):
    """
    Base class for TagFilter and ObjectFilter classes.
    """
    def __init__(self):
        self.atom = None
        self.__limit = self.__offset = 0

    def isPasses(self, obj):
        return bool(obj) if not self.atom else self.atom.isPasses(obj)

    def generateSqlWhere(self):
        if not self.atom:
            q = _Filter_Disabled().generateSql()
        else:
            q = self.atom.generateSql()
        if self.__limit: q = q + ' limit ' + str(self.__limit)
        if self.__offset: q = q + ' offset ' + str(self.__offset)
        return q

    def __and__(self, other):
        # true and true = true
        if not self.atom and not other.atom:
            return self.create()
        else:
            return self.create(_Filter_And(self.atom, other.atom))

    def __or__(self, other):
        # true or x = true
        if not self.atom or not other.atom:
            return self.create()
        else:
            return self.create(_Filter_Or(self.atom, other.atom))

    def __invert__(self):
        # not true = false
        if not self.atom:
            return self.create(_Filter_Block())
        else:
            return self.create(_Filter_Not(self.atom))

    def block(self):
        # x and false = false
        return self.create(_Filter_Block())

    def limit(self, limit_value):
        f = copy.copy(self)
        f.__limit = limit_value
        return f

    def offset(self, offset_value):
        f = copy.copy(self)
        f.__offset = offset_value
        return f

class TagFilter(_Filter):
    """
    Tag filters allows checking if tag meets some criteria and also
    query library for such tags.
    Call to type creates filter that passes all tags.
    """

    @staticmethod
    def create(atom = None):
        f = TagFilter()
        f.atom = atom
        return f

    def tagClass(self, tag_class):
        """
        Receives tag identity or tag class or class name (str or Wildcard)
        """
        return self & self.create(_Tag_Class(tag_class))

    def identity(self, identity):
        """
        Matches only by identity. To match class and value use construct like this:
        TagFilter().tagClass().value()
        """
        return self & self.create(_Tag_Identity(identity))

    def number(self, number, op = '='):
        """
        Matches tags which have numeric value and which number comparision result using
        given operator with given value is true.
        """
        return self & self.create(_Tag_Number(number, op))

    def text(self, text):
        """
        Receives str or Wildcard argument
        """
        return self & self.create(_Tag_Text(text))

    def locator(self, locator):
        return self & self.create(_Tag_Locator(locator))

    def objectReference(self, object_reference):
        return self & self.create(_Tag_Object(object_reference))

    def none(self):
        """
        Match tags with value type = None
        """
        return self & self.create(_Tag_NoneValue())

    def valueType(self, value_type):
        return self & self.create(_Tag_ValueType(value_type))

    def unused(self):
        """
        Match tags not linked to any object. This filter has meaning only for flushed tags,
        and will not pass ones for which isValid == False
        """
        return self & self.create(_Tag_Unused())

    def value(self, value):
        return self & self.create(_Tag_Value(value))

    def linkedWith(self, object):
        """
        Matches tags that are linked with specified object. Note that actual object value (to comparision moment)
        is used (to avoid differences between in-memory checks and database queries). Filter will become
        blocked if constructed with unflushed object.
        """
        return self & self.create(_Tag_LinkedWith(object))

class _Tag_Class(object):
    """
    Matches tags with given class. Class can be specified with name or identity.
    Wildcard can be used to match class name.
    """
    def __init__(self, tag_class):
        self.__tagClass = tag_class

    def isPasses(self, tag):
        if not tag or not tag.className:
            return False

        if isinstance(self.__tagClass, Identity) or isinstance(self.__tagClass, TagClass):
            ident = get_identity(self.__tagClass)
            if not ident.isValid:
                if isinstance(self.__tagClass, TagClass):
                    # if we have filter basing on unflushed TagClass we will pass
                    # tag without flushed class and name equal to specified class name
                    return not tag.tagClass and tag.className.casefold() == \
                           self.__tagClass.name.casefold()
                else:
                    # filter is based on invalid Identity. We cannot do anything.
                    return False
            else:
                # orginary compare. Tag' class should be flushed.
                return tag.tagClass and tag.tagClass.identity == \
                       get_identity(self.__tagClass)
        elif isinstance(self.__tagClass, Wildcard):
            return self.__tagClass == tag.className
        else:
            return self.__tagClass and tag.className.casefold() == self.__tagClass.casefold()

    def generateSql(self):
        if isinstance(self.__tagClass, Identity) or isinstance(self.__tagClass, TagClass):
            ident = get_identity(self.__tagClass)
            if not ident.isValid:
                if isinstance(self.__tagClass, TagClass) and self.__tagClass.name:
                    return _Tag_Class(self.__tagClass.name).generateSql()
                else:
                    return _Filter_Block().generateSql()
            else:
                return "class_id = {0}".format(self.__tagClass.id)
        elif isinstance(self.__tagClass, str) or isinstance(self.__tagClass, Wildcard):
            if self.__tagClass:
                return "class_id in (select id from tag_classes where {0})" \
                       .format(generateSqlCompare('name', self.__tagClass))
        return _Tag_Block().generateSql()

class _Tag_Identity(object):
    """
    Matches tag with given identity
    """
    def __init__(self, identity):
        self.__identity = identity

    def isPasses(self, tag):
        return tag and tag.identity == get_identity(self.__identity)

    def generateSql(self):
        if self.__identity.isValid:
            return "id = {0}".format(self.__identity.id)
        else:
            return _Filter_Block().generateSql()

class _Tag_Text(object):
    def __init__(self, text):
        self.__text = text

    def isPasses(self, tag):
        if not tag: return False
        if isinstance(self.__text, Wildcard):
            return self.__text.isEqual(tag.value.text)
        else:
            return self.__text.casefold() == tag.value.text.casefold()

    def generateSql(self):
        return 'value_type = {0} and {1} collate strict_nocase'.format(TagValue.TYPE_TEXT,
                                                                       generateSqlCompare('value', self.__text))

class _Tag_Number(object):
    func_map = {
        '==': operator.eq,
        '=': operator.eq,
        '!=': operator.ne,
        '>': operator.gt,
        '<': operator.lt,
        '>=': operator.ge,
        '<=': operator.le
    }

    def __init__(self, number, op = '=='):
        self.__number = number
        if op not in self.func_map:
            raise ArgumentError('unknown operation {0}'.format(op))
        self.__op = op

    def isPasses(self, tag):
        return tag and tag.value.valueType == TagValue.TYPE_NUMBER and \
               self.func_map[self.__op](tag.value.number, self.__number)

    def generateSql(self):
        return "value_type = {0} and value {1} {2}".format(TagValue.TYPE_NUMBER,
                                                           self.__op, self.__number)

class _Tag_Locator(object):
    def __init__(self, locator):
        self.__locator = locator

    def isPasses(self, tag):
        return tag and tag.value.locator == self.__locator

    def generateSql(self):
        return "value_type = {0} and value = '{1}'".format(TagValue.TYPE_LOCATOR, \
                                                           self.__locator.databaseForm())

class _Tag_Object(object):
    def __init__(self, objectReference):
        self.__objectReference = objectReference

    def isPasses(self, tag):
        return tag and tag.value.objectReference == self.__objectReference

    def generateSql(self):
        if self.__objectReference.isValid:
            return 'value_type = {0} and value = {1}'.format(TagValue.TYPE_OBJECT_REFERENCE, \
                                                             self.__objectReference.id)
        else:
            return _Filter_Block().generateSql()

class _Tag_ValueType(object):
    def __init__(self, valueType):
        self.__valueType = valueType

    def isPasses(self, tag):
        return tag and tag.value.valueType == self.__valueType

    def generateSql(self):
        return "value_type = {0}".format(self.__valueType)

class _Tag_NoneValue(_Tag_ValueType):
    def __init__(self):
        super().__init__(TagValue.TYPE_NONE)

class _Tag_Value(object):
    def __init__(self, value):
        self.__value = TagValue(value)

    def isPasses(self, tag):
        return tag and tag.value == self.__value

    def generateSql(self):
        if self.__value.valueType == TagValue.TYPE_TEXT:
            return _Tag_Text(self.__value.text).generateSql()
        elif self.__value.valueType == TagValue.TYPE_NUMBER:
            return _Tag_Number(self.__value.number).generateSql()
        elif self.__value.valueType == TagValue.TYPE_LOCATOR:
            return _Tag_Locator(self.__value.locator).generateSql()
        elif self.__value.valueType == TagValue.TYPE_OBJECT_REFERENCE:
            return _Tag_Object(self.__value.objectReference).generateSql()
        elif self.__value.valueType == TagValue.TYPE_NONE:
            return _Tag_NoneValue().generateSql()
        else:
            raise TypeError()

class _Tag_Unused(object):
    def isPasses(self, tag):
        if not tag or not tag.isValid: return False
        return not tag.lib.objects(ObjectFilter().tags(tag).limit(1))

    def generateSql(self):
        return 'id not in (select distinct tag_id from links)'

class _Tag_LinkedWith(object):
    def __init__(self, object):
        self.object = object

    def isPasses(self, tag):
        if not isinstance(self.object, (Identity, Object)):
            raise TypeError()
        obj = self.object.lib.object(self.object)
        return obj.testTag(tag)

    def generateSql(self):
        if self.object and self.object.isValid:
            return 'id in (select tag_id from links where object_id = {0})' \
                   .format(self.object.id)
        else:
            return _Filter_Block().generateSql()

#####################################################################33

class ObjectFilter(_Filter):
    @staticmethod
    def create(atom = None):
        f = ObjectFilter()
        f.atom = atom
        return f

    def displayName(self, display_name):
        """Matches objects with displayNameTemplate equal to given. Allows Wildcard as argument"""
        return self & self.create(_Object_DisplayName(display_name))

    def identity(self, obj):
        return self & self.create(_Object_Identity(obj))

    def tags(self, tags_filter):
        """Matches objects that have at least one tag that can pass filter"""
        return self & self.create(_Object_Tags(tags_filter))

    def withoutTags(self):
        """Matches objects that have no tags linked"""
        return self & self.create(_Object_WithoutTags())

class _Object_DisplayName(object):
    def __init__(self, display_name):
        self.__displayName = display_name

    def isPasses(self, obj):
        return obj and self.__displayName == obj.displayNameTemplate

    def generateSql(self):
        return generateSqlCompare('display_name', self.__displayName)

class _Object_Identity(object):
    def __init__(self, obj):
        self.__identity = obj

    def isPasses(self, obj):
        if not obj: return False
        if isinstance(self.__identity, Object):
            return self.__identity.identity == obj.identity
        else:
            return self.__identity == obj.identity

    def generateSql(self):
        if self.__identity.isValid:
            return "id = {0}".format(self.__identity.id)
        else:
            return _Filter_Block().generateSql()

class _Object_Tags(object):
    def __init__(self, f):
        if isinstance(f, (str, Wildcard, TagClass)):
            self.__tagFilter = TagFilter().tagClass(f)
        elif isinstance(f, (Tag, Identity)):
            self.__tagFilter = TagFilter().identity(f)
        else:
            self.__tagFilter = f

    def isPasses(self, obj):
        return obj.testTag(self.__tagFilter)

    def generateSql(self):
        return 'id in (select object_id from links where tag_id in ' \
               '(select id from tags where {0}))'.format(self.__tagFilter.generateSqlWhere())

class _Object_WithoutTags(object):
    def isPasses(self, obj):
        return obj and not obj.allTags

    def generateSql(self):
        return 'id not in (select distinct object_id from links)'
