import unittest
import organica.lib.library as library
import organica.lib.objects as objects
from organica.lib.objects import TagValue, Identity
from organica.lib.library import LibraryError
from organica.lib.filters import Wildcard


class TestLibraryMeta(unittest.TestCase):
    def setUp(self):
        self.lib = library.Library.createLibrary(':memory:')

    def tearDown(self):
        self.lib.disconnect()

    def test(self):
        self.lib.setMeta('meta1', 'meta1_value')
        self.assertTrue(self.lib.testMeta('meta1'))
        self.assertEqual(self.lib.getMeta('meta1'), 'meta1_value')

        self.lib.setMeta('meta1', 'meta1_value2')
        self.assertTrue(self.lib.testMeta('meta1'))
        self.assertEqual(self.lib.getMeta('meta1'), 'meta1_value2')

        self.lib.setMeta('meta1', 'meta1_value2')
        self.assertTrue(self.lib.testMeta('meta1'))
        self.assertEqual(self.lib.getMeta('meta1'), 'meta1_value2')

        self.lib.setMeta('meta2', 'meta2_value')
        self.assertTrue(self.lib.testMeta('meta1') and self.lib.testMeta('meta2'))

        self.assertEqual(self.lib.allMeta, {'meta1': 'meta1_value2',
                                             'meta2': 'meta2_value',
                                             'organica': 'is magic'})

        self.lib.removeMeta('meta1')
        self.assertTrue(not self.lib.testMeta('meta1'))
        self.assertEqual(self.lib.getMeta('meta1'), '')
        self.assertEqual(self.lib.allMeta, {'meta2': 'meta2_value',
                                             'organica': 'is magic'})

        self.assertFalse(objects.isCorrectIdent('meta!'))
        self.assertTrue(objects.isCorrectIdent('meta2_name'))


class TestLibraryTagClasses(unittest.TestCase):
    def setUp(self):
        self.lib = library.Library.createLibrary(':memory:')

    def tearDown(self):
        self.lib.disconnect()

    def test(self):
        # createTagClass
        class_author = self.lib.createTagClass('author', TagValue.TYPE_TEXT)
        self.assertTrue(class_author)
        self.assertEqual(class_author.name, 'author')
        self.assertEqual(class_author.valueType, TagValue.TYPE_TEXT)
        self.assertEqual(class_author.hidden, False)
        self.assertEqual(class_author, self.lib.createTagClass('author'))

        with self.assertRaises(TypeError):
            self.lib.createTagClass('what_the_f**k')

        with self.assertRaises(TypeError):
            self.lib.createTagClass('another_class', 2988)

        # tagClass
        class_author = self.lib.tagClass('author')
        self.assertEqual(class_author.name, 'author')
        self.assertTrue(class_author.isFlushed)

        class_author = self.lib.tagClass(class_author.identity)
        self.assertEqual(class_author.name, 'author')
        self.assertTrue(class_author.isFlushed)

        class_author = self.lib.tagClass('book')
        self.assertFalse(class_author)

        self.assertFalse(self.lib.tagClass(Identity(self.lib, 200)))

        # tagClasses
        classes = self.lib.tagClasses('author')
        self.assertListEqual(classes, [self.lib.tagClass('author')])

        classes = self.lib.tagClasses(Wildcard('a*'))
        self.assertListEqual(classes, [self.lib.tagClass('author')])
