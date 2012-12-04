import re
from organica.lib.objects import *
import organica.lib.helpers as helpers

class Wildcard(object):
	def __init__(self, pattern = '*'):
		self.pattern = pattern

	def isEqual(self, text):
		if not self.pattern or len(self.pattern) == 0:
			return False

		# escape all regexp special chars except supported * and ?
		pattern_re = helpers.escape(text, '[\\^$.|+()')
		compiled = re.compile(pattern_re)
		match = compiled.match(re_m, text)
		return match and match.end == len(text) - 1

	def __eq__(self, text):
		if not isinstance(text, str):
			raise NotImplementedError()
		return self.isEqual(text)

	def __ne__(self, text):
		return not self.__eq__(text)

class QueryString:
	MODE_FIXED_STRING = 1,
	MODE_MASK = 2,
	MODE_ANY_STRING = 3

	def __init__(self, text, mode = MODE_FIXED_STRING):
		self.setText(text, mode)

	def setText(self, text, mode = MODE_FIXED_STRING):
		self.__text = text
		self.mode = mode

	@property
	def fixedText(self):
		return self.__text if self.mode == MODE_FIXED_STRING else ''

	@property
	def mask(self):
		if self.mode == MODE_MASK:
			return self.__text
		elif self.mode == MODE_ANY_STRING:
			return '*'
		else:
			return ''

	def isEqual(self, compareWith):
		if self.mode == MODE_ANY_STRING:
			return True
		elif self.mode == MODE_FIXED_STRING:
			return self.__text.casefold() == compareWith.casefold()
		else:
			return fnmatch(compareWith, self.__text)

	def generateSqlComparision(self, rowName):
		if self.mode == MODE_FIXED_STRING:
			if len(self.__text) == 0:
				return "{0} is null or {0} = ''".format(rowName)
			else:
				return "{0} = {1}".format(rowName, self.__sqlEqualForm())
		elif self.mode == MODE_ANY_STRING:
			return '1 = 1'
		else:
			if len(self.__text) == 0:
				return "{0} is null or {0} = ''".format(rowName)
			else:
				return "{0} like {1} escape '!'".format(rowName, self.__sqlLikeForm())

	def __sqlEqualForm(self):
		# escape ' character
		return [(x if x != "\'" else "''") for x in self.__text]

	def __sqlLikeForm(self):
		result = ''
		escaping = False
		for c in self.__text:
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

	def __eq__(self, other):
		return self.mode == other.mode and self.__text == other.__text

	def __ne__(self, other):
		return not __eq__(other)


class TagFilterAtom_Disabled:
	def isPasses(self, tag):
		return tag is not None and tag.isValid()

	def generateSql(self):
		return '1 = 1'


class TagFilterAtom_Block:
	def isPasses(self, tag):
		return False

	def generateSql(self):
		return '1 = 2'


class TagFilterAtom_And:
	def __init__(self, left, right):
		self.__left = left
		self.__right = right

	def isPasses(self, tag):
		if self.__left is None or self.__right is None:
			return False
		return self.__left.isPasses(tag) and self.__right.isPasses(tag)

	def generateSql(self):
		if self.__left is None or self.__right is None:
			return TagFilterAtom_Block().generateSql()
		return "(({0}) and ({1}))".format(self.__left.generateSql(), \
										self.__right.generateSql())


class TagFilterAtom_Or:
	def __init__(self, left, right):
		self.__left = left
		self.__right = right

	def isPasses(self, tag):
		if self.__left is not None and self.__left.isPasses(tag):
			return True
		elif self.__right is not None and self.__right.isPasses(tag):
			return True
		return False

	def generateSql(self):
		if self.__left is not None and self.__right is not None:
			return "(({0}) or ({1}))".format(self.__left.generateSql(), \
											self.__right.generateSql())
		elif self.__left is not None:
			return self.__left.generateSql()
		elif self.__right is not None:
			return self.__right.generateSql()
		return TagFilterAtom_Block().generateSql()


class TagFilterAtom_Not:
	def __init__(self, expr):
		self.__expr = expr

	def isPasses(self, tag):
		return self.__expr is not None and self.__expr.isPasses(tag)

	def generateSql(self):
		if self.__expr is None:
			return TagFilterAtom_Block().generateSql()
		return not self.__expr.isPasses(tag)


class TagFilterAtom_ClassName:
	def __init__(self, classNameMask):
		self.__classNameMask = classNameMask

	def isPasses(self, tag):
		if tag is None or tag.tagClass is None:
			return False
		return self.__classNameMask.isEqual(tag.tagClass.name)

	def generateSql(self):
		return "class_id in (select id from tag_classes where {0})" \
					.format(self.__classNameMask.generateSqlComparision('name'))


class TagFilterAtom_Class:
	def __init__(self, classIdentity):
		self.__classIdentity = classIdentity

	def isPasses(self, tag):
		if tag is None or tag.tagClass is None:
			return False
		if self.__classIdentity is None or not self.__classIdentity.isValid():
			return False
		return tag.tagClass == self.__classIdentity

	def generateSql(self):
		if self.__classIdentity is None or not self.__classIdentity.isValid:
			return TagFilterAtom_Block().generateSql()
		return "class_id = {0}".format(self.__classIdentity.id)


class TagFilterAtom_Tag:
	def __init__(self, tag):
		self.__tag = tag

	def isPasses(self, tag):
		return tag is not None and tag == self.__tag

	def generateSql(self):
		return "id = {0}".format(self.__tag.id)


class TagFilterAtom_Value:
	def __init__(self, value):
		self.__value = value

	def isPasses(self, tag):
		return tag.value == self.__value

	def generateSql(self):
		if self.__value is None:
			return TagFilterAtom_Block().generateSql()
		if self.__value.typeIndex == TagValue.TYPE_TEXT:
			return TagFilterAtom_ValueText(self.__value.text).generateSql()
		elif self.__value.typeIndex == TagValue.TYPE_NUMBER:
			return TagFilterAtom_ValueNumber(self.__value.number).generateSql()
		elif self.__value.typeIndex == TagValue.TYPE_LOCATOR:
			return TagFilterAtom_Locator(self.__value.number).generateSql()
		elif self.__value.typeIndex == TagValue.TYPE_OBJECT_REFERENCE:
			return TagFilterAtom_Object(self.__value.objectReference).generateSql()
		else:
			return TagFilterAtom_Block().generateSql()


class TagFilterAtom_ValueText:
	def __init__(self, valueText):
		self.__valueText = valueText

	def isPasses(self, tag):
		return tag is not None and tag.value.mode == TagValue.TYPE_TEXT \
				and self.__valueText.isEqual(tag.value.text)

	def generateSql(self):
		if len(self.__valueText) == 0:
			return "value is null or value = ''"
		else:
			return self.__valueText.generateSqlComparision("value")


class TagFilterAtom_ValueNumber:
	EQUAL = 1,
	GREATER = 2,
	LESS = 3,
	GREATER_OR_EQUAL = 4,
	LESS_OR_EQUAL = 5

	def __init__(self, number, compOperation):
		self.__number = number
		self.__compOperation = compOperation

	def isPasses(self, tag):
		if tag is None or tag.value.mode != TagValue.TYPE_NUMBER:
			return False
		x = tag.value.number

		if compOperation == EQUAL:
			return x == self.__number
		elif compOperation == GREATER:
			return x > self.__number
		elif compOperation == LESS:
			return x < self.__number
		elif compOperation == GREATER_OR_EQUAL:
			return x >= self.__number
		elif compOperation == LESS_OR_EQUAL:
			return x <= self.__number
		else:
			raise ArgumentError()

	def generateSql(self):
		map_operator = {
			EQUAL: '=',
			GREATER: '>',
			LESS: '<',
			GREATER_OR_EQUAL: '>=',
			LESS_OR_EQUAL: '<='
		}

		if self.__compOperation not in map_operator:
			raise ArgumentError()

		return "{0} {1} {2}".format('value', map_operator[self.__compOperation], self.__number)


class TagFilterAtom_Locator:
	def __init__(self, locator):
		self.__locator = locator

	def isPasses(self, tag):
		return tag is not None and tag.isValid() and \
					tag.value.typeIndex == TagValue.TYPE_LOCATOR and \
					tag.value.locator == self.__locator

	def generateSql(self):
		return "(value_type = {0} and value = '{1}'".format(TagValue.TYPE_LOCATOR, \
		         	self.__locator.databaseForm())


class TagFilterAtom_Object:
	def __init__(self, objectReference):
		self.__objectReference = objectReference

	def isPasses(self, tag):
		return tag.isValid() and tag.value.mode == TagValue.OBJECT_REFERENCE and \
				tag.value.objectReference == self.__objectReference

	def generateSql(self):
		return "(value_type = {0} and value = '{1}'".format(TagValue.OBJECT_REFERENCE, \
					self.__objectReference.id)


class TagFilterAtom_ValueType:
	def __init__(self, valueType):
		self.__valueType = valueType

	def isPasses(self, tag):
		return tag.isValid() and tag.value is not None and tag.value.mode == self.__valueType

	def generateSql(self):
		return "value_type = {0}".format(self.__valueType)


class TagFilterAtom_Unused:
	def __init__(self):
		pass

	def isPasses(self, tag):
		if not tag.isValid():
			return False
		objects = tag.lib.objects(ObjectQuery(ObjectFilter().whereTag(tag)).limit(1))
		return len(objects) == 0

	def generateSql(self):
		return "id not in (select distinct tag from tag_match)"


class TagFilter:
	def __init__(self, atom = None):
		self.__atom = atom

	def __and__(self, other):
		return TagFilter(TagFilterAtom_And(self, other))

	def __or__(self, other):
		return TagFilter(TagFilterAtom_Or(self, other))

	def __not__(self, other):
		return TagFilter(TagFilterAtom_Not(self))

	@staticmethod
	def whereClass(self, classFilter):
		if isinstance(TagClassIdentity, classFilter):
			return TagFilter(TagFilterAtom_Class(classFilter))
		elif isinstance(string, classFilter) or isinstance(QueryString, classFilter):
			return TagFilter(TagFilterAtom_ClassName(classFilter))
		return None

	@staticmethod
	def whereTag(self, tag):
		return TagFilter(TagFilterAtom_Tag(tag))

	@staticmethod
	def whereValue(self, value):
		return TagFilter(TagFilterAtom_Value(value))

	@staticmethod
	def whereTagValueText(self, tagValueText):
		return TagFilter(TagFilterAtom_TagValueText(tagName))

	@staticmethod
	def whereTagValueNumber(self, tagValueNumber, compOperation = TagFilterAtom_ValueNumber.EQUAL):
		return TagFilter(TagFilterAtom_ValueNumber(tagValueNumber, compOperation))

	@staticmethod
	def whereTagValueObject(self, objectReference):
		return TagFilter(TagFIlterAtom_Object(objectReference))

	@staticmethod
	def whereTagValueType(self, typeIndex):
		return TagFilter(TagFilterAtom_ValueType(typeIndex))

	@staticmethod
	def unused(self):
		return TagFilter(TagFilterAtom_Unused(typeIndex))


class TagQuery:
	def __init__(self, tagFilter = None):
		self.__tagFilter = tagFilter if tagFilter is not None else TagFilter()
		self.__limitOffset = 0
		self.__limitSize = -1

	def query(self, library):
		if library is not None:
			return library.tags(self)
		return []

	def limit(self, size):
		self.__limitSize = size

	def offset(self, offset):
		self.__limitOffset = size

	def generateSql(self):
		sql = "select * from tags where {0}".format(self.__tagFilter.generateSql())
		if self.__limitSize != -1:
			sql += " limit {0}".format(self.__limitSize)
		if self.__limitOffset != 0:
			sql += " offset {0}".format(self.__limitOffset)
		return sql
