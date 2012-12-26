import unittest
from organica.lib.objects import Identity, Object, Tag, TagClass, TagValue
from organica.lib.filters import TagFilter, ObjectFilter

class TestTagValue(unittest.TestCase):
    def test(self):
        value = TagValue('string')
        self.assertEqual(value.valueType, TagValue.TYPE_TEXT)
        self.assertEqual(value.text, 'string')

        value = TagValue(89)
        self.assertEqual(value.valueType, TagValue.TYPE_NUMBER)
        self.assertEqual(value.number, 89)

        value = TagValue()
        self.assertEqual(value.valueType, TagValue.TYPE_NONE)
        self.assertNotEqual(value, TagValue())

class TestTagClass(unittest.TestCase):
    def test(self):
        tclass = TagClass('new_class')
        self.assertEqual(tclass.name, 'new_class')
        self.assertEqual(tclass.valueType, TagValue.TYPE_TEXT)
        self.assertEqual(tclass.hidden, False)
        self.assertFalse(tclass.identity.isValid)

        self.assertEqual(tclass, TagClass('NEW_CLASS'))

class TestTag(unittest.TestCase):
    def test(self):
        tag = Tag('author', 'Lewis Carrol')
        self.assertEqual(tag.className, 'author')
        self.assertEqual(tag.tagClass, None) # as tag class was not created
        self.assertEqual(tag.value, 'Lewis Carrol')

        self.assertTrue(tag.passes(tag))
        self.assertFalse(tag.passes(Tag()))

class TestObject(unittest.TestCase):
    def test(self):
        object = Object('some book', {'author': 'Lewis Carrol', 'page_count': 128})
        self.assertEqual(object.displayNameTemplate, 'some book')
        self.assertTrue(len(object.allTags), 2)
