import unittest
from organica.lib.objects import Node, Tag, TagValue
from organica.lib.library import Library


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
        lib = Library.createLibrary(':memory:')
        tclass = lib.createTagClass('new_class')

        self.assertEqual(tclass.name, 'new_class')
        self.assertEqual(tclass.valueType, TagValue.TYPE_TEXT)
        self.assertEqual(tclass.hidden, False)


class TestTag(unittest.TestCase):
    def test(self):
        lib = Library.createLibrary(':memory:')
        author_class = lib.createTagClass('author')

        tag = Tag(author_class, 'Lewis Carrol')
        self.assertEqual(tag.className, 'author')
        self.assertEqual(tag.tagClass, author_class)
        self.assertEqual(tag.value, 'Lewis Carrol')
        self.assertEqual(tag.value.valueType, TagValue.TYPE_TEXT)

        self.assertTrue(tag.passes(tag))
        self.assertFalse(tag.passes(Tag()))


class TestNode(unittest.TestCase):
    def test(self):
        lib = Library.createLibrary(':memory:')
        author_class = lib.createTagClass('author')
        page_count_class = lib.createTagClass('page_count')

        node = Node('some_book', (Tag(author_class, 'Lewis Carrol'), Tag(page_count_class, 128)))
        self.assertEqual(node.displayNameTemplate, 'some_book')
        self.assertTrue(len(node.allTags), 2)
        anode = node.flush(lib)

        self.assertTrue(anode.isFlushed)
        self.assertTrue(Tag(author_class, 'Lewis Carrol') in anode.allTags)
        self.assertTrue(Tag(page_count_class, 128) in anode.allTags)
        self.assertEqual(len(anode.allTags), 2)

        year_class = lib.createTagClass('year', TagValue.TYPE_NUMBER)
        anode.link(Tag(year_class, 1855))
        self.assertTrue(Tag(year_class, 1855) in anode.allTags)
        anode = anode.flush()

        self.assertEqual(len(anode.allTags), 3)
        self.assertTrue(Tag(year_class, 1855) in anode.allTags)
