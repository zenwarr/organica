import re
import operator
import copy

import organica.utils.helpers as helpers
from organica.lib.objects import Tag, TagClass, TagValue, Identity, get_identity


class Wildcard(object):
    """Simple mask used to match string. Allows only * and ? characters. Matching is not case sensitive.
    To match string simply compare wildcard with string. Wildcard is immutable (just like string).
    Default constructed Wildcard matches empty strings.
    """

    def __init__(self, pattern=''):
        self.pattern = pattern if not isinstance(pattern, Wildcard) else pattern.pattern

    def isEqual(self, text):
        """Check if given string matches pattern.
        """

        if not self.pattern:
            return not text

        if not text:
            return False

        # generate regular expression we can use
        # escape all regexp special chars except * and ?
        pattern_re = helpers.escape(self.pattern, '[\\^$.|+()') + '$'
        # and translate wildcard special chars to regexp
        pattern_re = pattern_re.replace('*', '.*').replace('?', '.?')
        return bool(re.compile(pattern_re, re.IGNORECASE).match(text))

    def __eq__(self, text):
        """Comparing with string will cause wildcard matching; comparing with another
        Wildcard causes comparing patterns. Note that pattern equality does not mean wildcards
        are logically equal.
        """

        if isinstance(text, Wildcard):
            return self.pattern.casefold() == text.pattern.casefold()
        elif isinstance(text, str):
            return self.isEqual(text)
        else:
            return NotImplemented

    def __ne__(self, text):
        return not self.__eq__(text)


def _sqlEqualForm(text):
    """Doubles each single quote. Use it to sanitize strings which will be passed
    into query in constucts like this: row = 'some_text'
    """

    r = ''
    for x in text:
        r = r + (x if x != "\'" else "''")
    return r


def _sqlLikeForm(text):
    """Escapes string for use with LIKE ? ESCAPE '!'.
    Only recognized escape sequences are \*, \? and \\
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
                "'": "''"
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
    """Generate sql equal or LIKE comparision depending on type of template.
    If template is None, generated comparision will be TRUE only on empty strings or NULLs.
    Code assumes that row_name is safe and does not contains dangerous characters.
    """

    if not template:
        return "{0} = '' or {0} is null".format(row_name)
    elif isinstance(template, Wildcard):
        return "{0} like '{1}' escape '!'".format(row_name, _sqlLikeForm(template.pattern))
    else:
        return "{0} = '{1}'".format(row_name, _sqlEqualForm(template))


class _Filter_Disabled(object):
    """Disabled filter passes all tags.
    """

    def passes(self, tag):
        return tag is not None

    def generateSql(self):
        return '1 = 1'

    def qeval(self):
        return 1


class _Filter_Block(object):
    """Blocked filter passes no tags
    """

    def passes(self, obj):
        return False

    def generateSql(self):
        return '1 = 2'

    def qeval(self):
        return 0


class _Filter_And(object):
    """This filter is TRUE only when :left: and :right: filters are TRUE. If one
    of these filters is evaluated to False, it considered to be disabled (always TRUE).
    """

    def __init__(self, left, right):
        self.__left = left or _Filter_Disabled()
        self.__right = right or _Filter_Disabled()

    def passes(self, obj):
        if obj is None:
            return False

        return self.__left.passes(obj) and self.__right.passes(obj)

    def generateSql(self):
        if self.qeval() == -1:
            if self.__left.qeval() == -1 and self.__right.qeval() == -1:
                return '({0}) and ({1})'.format(self.__left.generateSql(),
                                              self.__right.generateSql())
            elif self.__left.qeval() == -1:
                return self.__left.generateSql()
            else:
                return self.__right.generateSql()
        elif self.qeval() == 1:
            return _Filter_Disabled().generateSql()
        else:
            return _Filter_Block().generateSql()

    def qeval(self):
        left = self.__left.qeval() if self.__left else 1
        right = self.__right.qeval() if self.__right else 1

        if left == 0 or right == 0:
            return 0
        elif left == 1 and right == 1:
            return 1
        else:
            return -1


class _Filter_Or(object):
    """This filter is TRUE if at least one of :left: and :right: filters is TRUE.
    Calculation is lazy: if first filter is passed, second one will not be checked.
    """

    def __init__(self, left, right):
        self.__left = left or _Filter_Disabled()
        self.__right = right or _Filter_Disabled()

    def passes(self, obj):
        if obj is None:
            return False

        return self.__left.passes(obj) or self.__right.passes(obj)

    def generateSql(self):
        if self.qeval() == -1:
            if self.__left.qeval() == -1 and self.__right.qeval() == -1:
                return '({0}) or ({1})'.format(self.__left.generateSql(),
                                               self.__right.generateSql())
            elif self.__left.qeval() == 0:
                return self.__right.qeval()
            else:
                return self.__left.qeval()
        elif self.qeval() == 1:
            return _Filter_Disabled().generateSql()
        else:
            return _Filter_Block().generateSql()

    def qeval(self):
        left = self.__left.qeval() if self.__left else 1
        right = self.__right.qeval() if self.__right else 1

        if left == 1 or right == 1:
            return 1
        elif left == 0 and right == 0:
            return 0
        else:
            return -1


class _Filter_Not(object):
    """Inverts value of another filter.
    """

    def __init__(self, expr):
        self.__expr = expr or _Filter_Disabled()

    def passes(self, obj):
        if obj is None:
            return False

        return not self.__expr.passes(obj)

    def generateSql(self):
        if self.qeval() == -1:
            return 'not ({0})'.format(self.__expr.generateSql())
        elif self.qeval() == 1:
            return _Filter_Disabled().generateSql()
        else:
            return _Filter_Block().generateSql()

    def qeval(self):
        expr_q = self.__expr.qeval()
        if expr_q == 0:
            return 1
        elif expr_q == 1:
            return 0
        else:
            return -1


class _Query(object):
    """Base class for TagQuery and NodeQuery classes.
    """

    def __init__(self, m_filter):
        super().__init__()
        self.__filter = m_filter or _Filter_Disabled()
        self.__limit = self.__offset = 0

    def filter(self, filter_object):
        """AND's current query with another one, returning new _Query
        """

        q = copy.copy(self)
        q.__filter = _Filter_And(self.__filter, filter_object)
        return q

    def limit(self, limit_count):
        """Limits result count to :limit_count:
        """

        q = copy.copy(self)
        q.__limit = limit_count
        return q

    def offset(self, offset_count):
        """Make first :offset_count: results to be omitted from resulting set
        """

        q = copy.copy(self)
        q.__offset = offset_count
        return q

    def __and__(self, other):
        """AND's filters of two queries
        """

        # True and True = True
        if not self.__filter and not other.__filter:
            return copy.copy(self)
        else:
            q = copy.copy(self)
            q.__filter = _Filter_And(self.__filter, other.__filter)
            return q

    def __or__(self, other):
        """OR's filters of two queries
        """

        # True or x = True
        if not self.__filter or not other.__filter:
            q = copy.copy(self)
            q.__filter = _Filter_Disabled()
            return q
        else:
            q = copy.copy(self)
            q.__filter = _Filter_Or(self.__filter, other.__filter)
            return q

    def __invert__(self):
        """Invert filter or this query.
        """

        # not True = False
        if not self.__filter:
            q = copy.copy(self)
            q.__filter = _Filter_Block()
            return q
        else:
            q = copy.copy(self)
            q.__filter = _Filter_Not(self.__filter)
            return q

    def blocked(self):
        q = copy.copy(self)
        q.__filter = _Filter_Block()
        return q

    def disabled(self):
        q = copy.copy(self)
        q.__filter = _Filter_Disabled()
        return q

    def passes(self, lib_object):
        return self.__filter.passes(lib_object)

    def generateSqlWhere(self):
        if not self.__filter:
            q = _Filter_Disabled().generateSql()
        else:
            q = self.__filter.generateSql()
        if self.__limit:
            q = q + ' limit ' + str(self.__limit)
        if self.__offset:
            q = q + ' offset ' + str(self.__offset)
        return q

    def qeval(self):
        return self.__filter.qeval()


####################################################################################


class _Tag_Class(object):
    def __init__(self, tag_class):
        self.tagClass = tag_class

    def passes(self, tag):
        if tag is None:
            return False

        if isinstance(self.tagClass, (Identity, TagClass)):
            return tag.tagClass == self.tagClass
        elif isinstance(self.tagClass, Wildcard):
            return self.tagClass == tag.className
        else:
            return tag.className.casefold() == self.tagClass.casefold()

    def generateSql(self):
        if isinstance(self.tagClass, (Identity, TagClass)):
            if self.tagClass.isFlushed:
                return "class_id = {0}".format(self.tagClass.id)
            else:
                return _Filter_Block().generateSql()
        else:
            return "class_id in (select id from tag_classes where {0})" \
                    .format(generateSqlCompare('name', self.tagClass))

    def qeval(self):
        return 0 if isinstance(self.tagClass, (Identity, TagClass)) and \
                not self.tagClass.isFlushed else -1


class _Tag_Identity(object):
    def __init__(self, identity):
        self.identity = get_identity(identity)

    def passes(self, tag):
        return tag is not None and self.identity == get_identity(tag)

    def generateSql(self):
        if self.identity.isFlushed:
            return "id = {0}".format(self.identity.id)
        else:
            return _Filter_Block().generateSql()

    def qeval(self):
        return 0 if not self.identity.isFlushed else -1


class _Tag_Text(object):
    def __init__(self, text):
        self.text = text

    def passes(self, tag):
        if tag is None or tag.value.valueType != TagValue.TYPE_TEXT:
            return False

        if isinstance(self.text, Wildcard):
            return self.text == tag.value.text
        else:
            return self.text.casefold() == tag.value.text.casefold()

    def generateSql(self):
        return 'value_type = {0} and {1} collate strict_nocase' \
                    .format(TagValue.TYPE_TEXT, generateSqlCompare('value', self.text))

    def qeval(self):
        return -1


class _Tag_Number(object):
    op_map = {
                'lt': '<',
                'le': '<=',
                'eq': '=',
                'ne': '!=',
                'ge': '>=',
                'gt': '>'
            }

    def __init__(self, number, op='eq'):
        self.number = number
        if op not in self.op_map:
            raise TypeError('TagFilter.number: unknown operation {0}'.format(op))
        self.op = op

    def passes(self, tag):
        op_func = getattr(operator, self.op)
        return tag is not None and tag.value.valueType == TagValue.TYPE_NUMBER and \
                op_func(tag.value.number, self.number)

    def generateSql(self):
        return "value_type = {0} and value {1} {2}" \
                    .format(TagValue.TYPE_NUMBER, _Tag_Number.op_map[self.op], self.number)

    def qeval(self):
        return -1


class _Tag_Locator(object):
    def __init__(self, locator):
        self.locator = locator

    def passes(self, tag):
        return tag is not None and tag.value.locator == self.locator

    def generateSql(self):
        return "value_type = {0} and value = '{1}'" \
                .format(TagValue.TYPE_LOCATOR, self.locator.databaseForm())

    def qeval(self):
        return -1


class _Tag_Object(object):
    def __init__(self, objectReference):
        self.objectReference = objectReference

    def passes(self, tag):
        return tag is not None and tag.value.objectReference == self.objectReference

    def generateSql(self):
        if self.objectReference.isFlushed:
            return 'value_type = {0} and value = {1}' \
                    .format(TagValue.TYPE_NODE_REFERENCE, self.objectReference.id)
        else:
            return _Filter_Block().generateSql()

    def qeval(self):
        return 0 if not self.objectReference.isFlushed else -1


class _Tag_ValueType(object):
    def __init__(self, valueType):
        self.valueType = valueType

    def passes(self, tag):
        return tag is not None and tag.value.valueType == self.valueType

    def generateSql(self):
        return "value_type = {0}".format(self.valueType)

    def qeval(self):
        return -1


class _Tag_NoneValue(_Tag_ValueType):
    def __init__(self):
        super().__init__(TagValue.TYPE_NONE)


class _Tag_Value(object):
    def __init__(self, value):
        self.value = TagValue(value)

    def passes(self, tag):
        return tag and tag.value == self.value

    def generateSql(self):
        if self.value.valueType == TagValue.TYPE_TEXT:
            return _Tag_Text(self.value.text).generateSql()
        elif self.value.valueType == TagValue.TYPE_NUMBER:
            return _Tag_Number(self.value.number).generateSql()
        elif self.value.valueType == TagValue.TYPE_LOCATOR:
            return _Tag_Locator(self.value.locator).generateSql()
        elif self.value.valueType == TagValue.TYPE_NODE_REFERENCE:
            return _Tag_Object(self.value.objectReference).generateSql()
        elif self.value.valueType == TagValue.TYPE_NONE:
            return _Tag_NoneValue().generateSql()
        else:
            raise TypeError()

    def qeval(self):
        return 0 if not TagValue.isValueTypeCorrect(self.value.valueType) else -1


class _Tag_Unused(object):
    def passes(self, tag):
        if tag is None or not tag.isFlushed:
            return False

        return not tag.lib.nodes(NodeQuery(tags=tag).limit(1))

    def generateSql(self):
        return 'id not in (select distinct tag_id from links)'

    def qeval(self):
        return -1


class _Tag_LinkedWith(object):
    def __init__(self, obj):
        self.node = obj

    def passes(self, tag):
        obj = self.node.lib.node(self.node)
        return obj is not None and obj.testTag(tag)

    def generateSql(self):
        if self.node.isFlushed:
            return 'id in (select tag_id from links where node_id = {0})' \
                   .format(self.node.id)
        else:
            return _Filter_Block().generateSql()

    def qeval(self):
        return 0 if not self.node.isFlushed else -1


class _Tag_Hidden(object):
    def __init__(self, is_hidden):
        self.is_hidden = is_hidden

    def passes(self, tag):
        return tag is not None and bool(tag.tagClass.hidden) == bool(self.is_hidden)

    def generateSql(self):
        return 'class_id in (select id from tag_classes where hidden = {0})' \
               .format(int(self.is_hidden))

    def qeval(self):
        return -1


class _Tag_FriendOf(object):
    def __init__(self, tag):
        self.tag = tag

    def passes(self, tag):
        if tag is None or not tag.isFlushed or self.qeval() == 0:
            return False

        return tag.lib == self.tag.lib and tag.isFriendOf(self.tag)

    def generateSql(self):
        if self.qeval() == 0:
            return _Filter_Block().generateSql()

        return 'id in (select tag_id from links where node_id in (select node_id from links where tag_id = {0}))' \
               .format(self.tag.id)

    def qeval(self):
        return 0 if self.tag is None or not self.tag.isFlushed else -1


class TagQuery(_Query):
    def __init__(self, **kwargs):
        _Query.__init__(self, self.__getFilter(**kwargs))

    def filter(self, **kwargs):
        """Get new query with filters AND'ed with filters of this query. Allowed arguments:
        identity:      matches tags with given identity
        value:         matches tags with given value
        tag_class:         matches tags with given tag class. Value of this argument can be string, Wildcard or
                       class Identity
        number:        matches tags with NUMBER value type and value equal to specified. To use >, < and other
                       operators, use number_xx where xx is operator name as specified in operators module
                       (one of lt, le, eq, ne, ge, gt)
        text:          matches tags with TEXT value type and value matching string or Wildcard
        locator:       matches tags with LOCATOR value type and given locator
        node_ref:      matches tags with OBJECT_REFERENCE value type which refers to given node Identity
        none:          matches tags with NONE value type. No value required for argument.
        value_type:    matches tags with given value type.
        unused:        matches only tags which are not linked to any nodes.
        linked_with:   matches only tags linked with specified nodes. Argument value should be object Identity
                       or sequence of Identities. Although you can still pass Node as argument,
                       still only identity will be used and each time comparision will be done actual
                       node value will be get from library.
        hidden:        matches tags that have given hidden class flag value.
        friend_of:     matches tags that are friends of given tags.
        """

        q = copy(self)
        q.__filter = self.__getFilter(**kwargs)
        return q

    __args_map = {
        'identity': _Tag_Identity,
        'value': _Tag_Value,
        'tag_class': _Tag_Class,
        'number': _Tag_Number,
        'text': _Tag_Text,
        'locator': _Tag_Locator,
        'node_ref': _Tag_Object,
        'value_type': _Tag_ValueType,
        'linked_with': _Tag_LinkedWith,
        'hidden': _Tag_Hidden,
        'friend_of': _Tag_FriendOf
    }

    def __getFilter(self, **kwargs):
        f = _Filter_Disabled()
        for arg in kwargs.keys():
            if arg in TagQuery.__args_map:
                f = _Filter_And(f, TagQuery.__args_map[arg](kwargs[arg]))
            elif arg == 'none':
                f = _Filter_And(f, _Tag_NoneValue())
            elif arg == 'unused':
                f = _Filter_And(f, _Tag_Unused())
            elif arg.startswith('number_'):
                f = _Filter_And(f, _Tag_Number(kwargs[arg], arg[7:]))
            else:
                raise TypeError('TagQuery.filter: unknown argument {0}'.format(arg))
        return f

TagFilter = TagQuery

#####################################################################33


class _Node_DisplayName(object):
    def __init__(self, display_name):
        self.displayName = display_name

    def passes(self, obj):
        return obj is not None and self.displayName == obj.displayNameTemplate

    def generateSql(self):
        return generateSqlCompare('display_name', self.displayName)

    def qeval(self):
        return -1


class _Node_Identity(object):
    def __init__(self, obj):
        self.identity = get_identity(obj)

    def passes(self, obj):
        return obj is not None and self.identity == get_identity(obj)

    def generateSql(self):
        if self.identity.isFlushed:
            return "id = {0}".format(self.identity.id)
        else:
            return _Filter_Block().generateSql()

    def qeval(self):
        return 0 if not self.identity.isFlushed else -1


class _Node_Tags(object):
    def __init__(self, f):
        if isinstance(f, (Tag, Identity)):
            self.tagFilter = TagQuery(identity=f)
        else:
            self.tagFilter = f

    def passes(self, obj):
        return obj is not None and obj.testTag(self.tagFilter)

    def generateSql(self):
        return ('id in (select node_id from links where tag_id in ' \
                + '(select id from tags where {0}))').format(self.tagFilter.generateSqlWhere())

    def qeval(self):
        return self.tagFilter.qeval()


class _Node_WithoutTags(object):
    def passes(self, obj):
        return obj is not None and not obj.allTags

    def generateSql(self):
        return 'id not in (select distinct node_id from links)'

    def qeval(self):
        return -1


class NodeQuery(_Query):
    def __init__(self, **kwargs):
        super().__init__(self.__getFilter(**kwargs))

    def filter(self, **kwargs):
        """Get new query with filters AND'ed with filters of this query. Allowed arguments:
        display_name:    matches nodes with given display name template. Can use string or Wildcard
                         as argument.
        identity:        matches nodes with given identity.
        tags:            matches nodes which have linked at least one tag satisfying given
                         condition.
        no_tags:         matches nodes which have no tags linked.
        tag_xx:          matches nodes which have at least one tag with given value linked. It is
                         just a shorthand instead of tags=TagFilter(tagClass=xx, value=yy).
        """

        q = copy(self)
        q.__filter = self.__getFilter(**kwargs)
        return q

    __args_map = {
        'display_name': _Node_DisplayName,
        'identity': _Node_Identity,
        'tags': _Node_Tags,
        'linked_with': _Node_Tags
    }

    def __getFilter(self, **kwargs):
        f = _Filter_Disabled()
        for arg in kwargs.keys():
            if arg in NodeQuery.__args_map:
                f = _Filter_And(f, NodeQuery.__args_map[arg](kwargs[arg]))
            elif arg == 'no_tags':
                f = _Filter_And(f, _Node_WithoutTags())
            elif arg.startswith('tag_'):
                f = _Filter_And(f, _Node_Tags(TagQuery(tagClass=arg[4:], value=kwargs[arg])))
            else:
                raise TypeError('NodeQuery.filter: unknown argument {0}'.format(arg))
        return f

NodeFilter = NodeQuery
