import re, operator
from organica.lib.objects import Object, Tag, TagClass, TagValue
import organica.utils.helpers as helpers

class Wildcard(object):
    def __init__(self, pattern = ''):
        if isinstance(pattern, Wildcard):
            self.pattern = pattern.pattern
        elif isinstance(pattern, str):
            self.pattern = pattern
        else:
            raise ArgumentError('pattern')

    def isEqual(self, text):
        if not self.pattern or len(self.pattern) == 0:
            return not text

        # escape all regexp special chars except supported * and ?
        pattern_re = helpers.escape(self.pattern, '[\\^$.|+()') + '$'
        pattern_re = pattern_re.replace('*', '.*').replace('?', '.?')
        return bool(re.compile(pattern_re).match(text))

    def __eq__(self, text):
        if not isinstance(text, str):
            return NotImplemented
        return self.isEqual(text)

    def __ne__(self, text):
        return not self.__eq__(text)

def _sqlEqualForm(text):
    """
    Doubles each single quote
    """
    return [(x if x != "\'" else "''") for x in text]

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
    if not template:
        return "({0} = '' or {0} is null)".format(row_name)
    elif isinstance(template, str):
        return "{0} = '{1}'".format(row_name, _sqlEqualForm(template))
    elif isinstance(template, Wildcard):
        return "{0} like {1} escape '!'".format(row_name, _sqlLikeForm(template))
    else:
        raise TypeError()


class _Filter_Disabled(object):
    def isPasses(self, tag):
        return bool(tag)

    def generateSql(self):
        return '1 = 1'

class _Filter_Block(object):
    def isPasses(self, obj):
        return False

    def generateSql(self):
        return '1 = 2'

class _Filter_And(object):
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
            return '(({0}) and ({1}))'.format(self.__left.generateSql(),
                                              self.__right.generateSql())
        elif not self.__left and not self.__right:
            return _Filter_Disabled().generateSql()
        else:
            return (self.__left if self.__left else self.__right).generateSql()

class _Filter_Or(object):
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
            return '(({0}) or ({1}))'.format(self.__left.generateSql(),
                                             self.__right.generateSql())
        else:
            return _Filter_Disabled().generateSql()

class _Filter_Not(object):
    def __init__(self, expr):
        self.__expr = expr

    def isPasses(self, obj):
        return self.__expr and not self.__expr.isPasses(obj)

    def generateSql(self):
        if not self.__expr:
            return _Filter_Block().generateSql()
        return 'not ({0})'.format(self.__expr.generateSql())

class _Filter(object):
    def __init__(self):
        self.__atom = None
        self.__limit = self.__offset = 0

    @staticmethod
    def create(atom):
        f = TagFilter()
        f.__atom = atom
        return f

    def isPasses(self, obj):
        return obj if not self.__atom else self.__atom.isPasses(obj)

    def generateSqlWhere(self):
        if not self.__atom:
            raise TypeError()
        q = self.__atom.generateSql()
        if self.__limit: q.append(' limit ' + str(self.__limit))
        if self.__offset: q.append(' offset ' + str(self.__offset))
        return q

    def __and__(self, other):
        # true and true = true
        if not self.__atom and not other.__atom:
            return TagFilter()
        else:
            return self.create(_Filter_And(self.__atom, other.__atom))

    def __or__(self, other):
        # true or x = true
        if not self.__atom or not other.__atom:
            return TagFilter()
        else:
            return self.create(_Filter_Or(self.__atom, other.__atom))

    def __not__(self):
        # not true = false
        if not self.__atom:
            return self.create(_Filter_Block())
        else:
            return self.create(_Filter_Not(self.__atom))

    def block(self):
        # x and false = false
        return self.create(_Filter_Block())

    def limit(self, limit_value):
        f = self
        f.__limit = limit_value
        return f

    def offset(self, offset_value):
        f = self
        f.__offset = offset_value
        return f

class TagFilter(_Filter):
    """
    Tag filters allows checking if tag meets some criteria and also
    query library for such tags.
    Call to type creates filter that passes all tags.
    """

    def tagClass(self, tag_class):
        """
        Receives tag identity or tag class or class name (str or Wildcard)
        """
        return self & self.create(_Tag_Class(tag_class))

    def tag(self, identity):
        return self & self.create(_Tag_Identity(identity))

    def number(self, number, op = '='):
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
        return self & self.create(_Tag_NoneValue())

    def valueType(self, value_type):
        return self & self.create(_Tag_ValueType(value_type))

    def unused(self):
        return self & self.create(_Tag_Unused())

    def value(self, value):
        return self & self.create(_Tag_Value(value))

    def linkedWith(self, object):
        return self & self.create(_Tag_LinkedWith(object))

class _Tag_Class(object):
    def __init__(self, tag_class):
        self.__tagClass = tag_class

    def isPasses(self, tag):
        if not tag or not tag.className:
            return False

        if isinstance(self.__tagClass, TagClass):
            return tag.tagClass == self.__tagClass
        elif isinstance(self.__tagClass, Identity):
            return tag.tagClass and tag.tagClass.identity() == self.__tagClass
        elif isinstance(self.__tagClass, str) or isinstance(self.__tagClass, Wildcard):
            return self.__tagClass == tag.className
        else:
            raise TypeError()

    def generateSql(self):
        if isinstance(self.__tagClass, Identity) or isinstance(self.__tagClass, TagClass):
            return "class_id = {0}".format(self.__tagClass.id)
        elif isinstance(self.__tagClass, str) or isinstance(self.__tagClass, Wildcard):
            return "class_id in (select id from tag_classes where {0}" \
                             .format(generateSqlCompare('name', self.__classNameMask))
        else:
            raise TypeError()

class _Tag_Identity(object):
    def __init__(self, identity):
        self.__identity = identity

    def isPasses(self, tag):
        if not tag: return False
        if isinstance(self.__identity, Tag):
            return self.__identity.identity == tag.identity
        elif isinstance(self.__identity, Identity):
            return self.__identity == tag.identity
        else:
            raise TypeError()

    def generateSql(self):
        return "id = {0}".format(self.__identity.id)

class _Tag_Text(object):
    def __init__(self, text):
        self.__text = text

    def isPasses(self, tag):
        return tag and self.__text == tag.value.text

    def generateSql(self):
        return '(value_type = {0} and {1})'.format(TagValue.TYPE_TEXT,
                                                  generateSqlCompare('value', self.text))

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
                self.func_map[self.__op](self.__number, tag.value.number)

    def generateSql(self):
        return "(value_type = {3} and {0} {1} {2})".format('value', self.__op,
                                                             self.__number,
                                                             TagValue.TYPE_NUMBER)

class _Tag_Locator(object):
    def __init__(self, locator):
        self.__locator = locator

    def isPasses(self, tag):
        return tag and tag.value.locator == self.__locator

    def generateSql(self):
        return "(value_type = {0} and value = '{1}')".format(TagValue.TYPE_LOCATOR, \
                     self.__locator.databaseForm())

class _Tag_Object(object):
    def __init__(self, objectReference):
        self.__objectReference = objectReference

    def isPasses(self, tag):
        return tag and tag.value.objectReference == self.__objectReference

    def generateSql(self):
        return '(value_type = {0} and value = {1})'.format(TagValue.OBJECT_REFERENCE, \
                    self.__objectReference.id)

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
        self.__value = value

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
        return tag.lib.objects(ObjectFilter().tag(tag).limit(1))

    def generateSql(self):
        return 'id not in (select distinct tag_id from links)'

class _Tag_LinkedWith(object):
    def __init__(self, object):
        self.object = object

    def isPasses(self, tag):
        obj = None
        if isinstance(self.object, Identity):
            obj = self.lib.object(self.object)
        else:
            obj = self.object
        return obj.testTag(tag)

    def generateSql(self):
        return 'id in (select tag_id from links where object_id = {0}' \
                       .format(self.object.id)

#####################################################################33

class ObjectFilter(_Filter):
    def displayName(self, display_name):
        return self & self.create(_Object_DisplayName(display_name))

    def object(self, obj):
        return self & self.create(_Object_Identity(obj))

    def tags(self, tags_filter):
        return self & self.create(_Object_Tags(tags_filter))

    def withoutTags(self):
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
        elif isinstance(self.__identity, Identity):
            return self.__identity == obj.identity
        else:
            raise TypeError()

    def generateSql(self):
        return "id = {0}".format(self.__identity.id)

class _Object_Tags(object):
    def __init__(self, tag_filter):
        self.__tagFilter = tag_filter

    def isPasses(self, obj):
        return obj.testTag(tag_filter)

    def generateSql(self):
        if isinstance(self.__tagFilter, str) or isinstance(self.__tagFilter, Wildcard) \
                or isinstance(self.__tagClass, TagClass):
            self.__tagFilter = TagFilter().tagClass(self.__tagFilter)
        elif isinstance(self.__tagClass, Tag) or isinstance(self.__tagClass, Identity):
            self.__tagFilter = TagFilter().tag(self.__tagClass)

        return 'id in (select object_id from links where tag_id in ' \
               '(select id from tags where {0}))'.format(self.__tagFilter.generateSql())

class _Object_WithoutTags(object):
    def isPasses(self, obj):
        return obj and not obj.allTags

    def generateSql(self):
        return 'id not in (select object_id from links)'
