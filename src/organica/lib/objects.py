from organica.lib.locator import Locator

class Identity
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
		return self.lib and self.id > 0

	def isIdentitiesEqual(self, other):
		return self.isValid and other.isValid and self.lib == other.lib and self.id == other.id

	def __eq__(self, other):
		return self.isIdentitiesEqual(other)

	def __ne__(self, other):
		return not self.isIdentitiesEqual(other)

class TagValue:
	TYPE_UNKNOWN = 0
	TYPE_TEXT = 1
	TYPE_NUMBER = 2
	TYPE_LOCATOR = 3
	TYPE_OBJECT_REFERENCE = 4

	def __init__(self, value, value_type = TYPE_UNKNOWN):
		self.setValue(value, value_type)

	def setValue(self, value, value_type):
		if value_type == self.TYPE_UNKNOWN:
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
		elif value_type == self.TYPE_LOCATOR:
			if not isinstance(value, Locator) and not isinstance(value, str):
				raise TypeError('invalid value for TagValue: Locator or str expected')
			self.value = Locator(value)
		elif value_type == self.TYPE_OBJECT_REFERENCE:
			if not isinstance(value, Object):
				raise TypeError('invalid value for TagValue: Object expected')
			self.value = value
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

	def databaseForm(self):
		"""
		Return dictionary of values that should be stored in database.
		Key is column name.
		"""
		if self.valueType == self.TYPE_TEXT or self.valueType == self.TYPE_NUMBER:
			return {'value': self.value}
		elif self.valueType == self.TYPE_LOCATOR:
			return {
					'scheme': self.value.scheme,
					'value': self.value.value
					}
		elif self.valueType == self.TYPE_OBJECT_REFERENCE:
			return {'value': '#{0}'.format(self.value.id)}
		else:
			return None

	@staticmethod
	def fromDatabaseForm(cTag, cTagClass, dbForm):
		result = TagValue()
		val = dbForm['value']
		if cTagClass.valueType == TYPE_TEXT:
			# database form should be text
			if not isinstance(str, val):
				raise TypeError('string expected for text tag')
			else:
				result.text = val
		elif cTagClass == TYPE_NUMBER:
			if not isinstance(int, val) and not isinstance(float, val):
				raise TypeError('number expected for number tag')
			else:
				result.number = val
		elif cTagClass == TYPE_OBJECT_REFERENCE:
			if not isinstance(str, val):
				raise TypeError('string expected for object reference')
			elif not val.startswith('#'):
				raise TypeError('bad format for object reference')
			else:
				objectId = int(val[1:])
				libObject = cTagClass.lib.object(objectId)
				if libObject is None:
					raise TypeError('invalid id #{0} for TYPE_OBJECT_REFERENCE tag' \
								.format(objectId))
				else:
					result.objectReference = libObject
		elif cTagClass == TYPE_LOCATOR:
			if not isinstance(string, val):
				raise TypeError('string expected for locator')
			result.locator = Locator.fromDatabaseForm(dbForm)
		return result

	def __eq__(self, other):
		if self.typeIndex != other.typeIndex:
			return False

		if self.typeIndex == TYPE_TEXT:
			return self.text() == other.text()
		elif self.typeIndex == TYPE_NUMBER:
			return self.number() == other.number()
		elif self.typeIndex == TYPE_OBJECT_REFERENCE:
			return self.objectReference() == other.objectReference()
		elif self.typeIndex == TYPE_LOCATOR:
			return self.locator == other.locator()
		else:
			return False

	def __ne__(self, other):
		return not self.__eq__(other)

	def typeString(self):
		typeMap = {TYPE_UNKNOWN: 'Unknown',
				   TYPE_TEXT: 'Text',
				   TYPE_NUMBER: 'Number',
				   TYPE_OBJECT_REFERENCE: 'Object reference',
				   TYPE_LOCATOR: 'Locator'}
		return typeMap[self.typeIndex] if typeMap.contains(self.typeIndex) else ''

class Tag(Identity):
	def __init__(self, lib = None, id = -1):
		super().__init__(lib, id)
		self.tagClass = None
		self.name = ''
		self.value = TagValue()

	def __m_eq(self, other):
		return self.tagClass == other.tagClass and self.name == other.name \
				and self.value == other.value

	def __eq__(self, other):
		if not self.isValid and not other.isValid:
			return self.__m_eq(other)
		else:
			return self.isIdentitiesEqual(other) and self.__m_eq(other)

	def __ne__(self, other):
		return not self.__eq__(other)

	def flush(self):
		if self.lib: self.lib.flush(self)

	def remove(self):
		if self.lib: self.lib.remove(self)

class TagClass(Identity):
	def __init__(self, lib = None, id = -1):
		super().__init__(lib, id)
		self.name = ''
		self.hidden = False
		self.valueType = TagValue.TYPE_UNKNOWN

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
			return self.isIdentitiesEqual(other) and self.__m_eq(other)

	def __ne__(self, other):
		return not self.__eq__(other)

class Object(Identity):
	def __init__(self, lib = None, id = -1):
		super().__init__(lib, id)
		self.locator = Locator()
		self.rawDisplayName = ''
		self.__allTags = []
		self.__tagsFetched = False

	@property
	def displayName(self):
		return FormatString(self.rawDisplayName, self).format()

	@property
	def allTags(self):
		self.__ensureTagsFetched()
		return self.__allTags

	@allTags.setter
	def setAllTags(self, value):
		self.__tagsFetched = True
		self.__allTags = value

	def tags(self, tag_filter):
		self.__ensureTagsFetched
		return [t for t in self.__allTags if tag_filter.passes(t)]

	def testTag(self, tag_filter):
		self.__ensureTagsFetched
		return contains(self.__allTags, lambda t: tag_filter.passes(t))

	@staticmethod
	def commonTags(objectList):
		if len(objectList) == 0:
			return []

		def check_t(tag, object):
			return object.testTag( \
					TagFilter.whereClass(tag.tagClass.name) and \
					TagFilter.whereValue(tag.value))

		result = objectList[0].allTags
		for obj in objectList[1:]:
			result = [t for t in result if check_t(t, obj)]
		return result

	def linkTag(self, tag):
		if not self.testTag(TagFilter.whereClass(tag.tagClass) and \
		                    TagFilter.whereValue(tag.value)):
			self.__allTags.append(tag)

	def createAndLinkTag(self, tagClass, tagValue):
		if not self.testTag(TagFilter.whereClass(tagClass) and \
				TagFilter.whereValue(tagValue)):
			self.__allTags.append(self.lib.getOrCreateTag(tagClass, tagValue))

	def unlinkTag(self, tag):
		self.__ensureTagsFetched()
		if tag not in self.__allTags:
			raise TagError('tag is not linked')
		self.__allTags.remove(tag)

	def removeTags(self, tag_filter):
		self.__ensureTagsFetched()
		self.__allTags.remove(lambda t: tag_filter.passes(t))

	def remove(self):
		if self.isValid(): self.lib.remove(self)

	def flush(self):
		if self.isValid(): self.lib.flush(self)

	def __m_eq(self, other):
		return self.rawDisplayName == other.rawDisplayName \
				and self.locator == other.locator \
				and self.allTags == other.allTags

	def __eq__(self, other):
		if not self.isValid() and not other.isValid():
			return self.__m_eq(other)
		else:
			return self.__m_eq(other) and super().__eq__(other)

	def __ne__(self, other):
		return not __eq__(other)

	def __ensureTagsFetched(self):
		if self.isValid() and not self.__tagsFetched:
			self.allTags = self.lib.objectTags(self)
		self.__tagsFetched = True

