import unittest
import organica.lib.library as library

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
		                 					'meta2': 'meta2_value'})

		self.lib.removeMeta('meta1')
		self.assertTrue(not self.lib.testMeta('meta1'))
		self.assertEqual(self.lib.getMeta('meta1'), '')
		self.assertEqual(self.lib.allMeta, {'meta2': 'meta2_value'})

		self.assertFalse(library.Library.isCorrectIdentifier('meta!'))
		self.assertTrue(library.Library.isCorrectIdentifier('meta2_name$'))

class TestLibraryTagClasses(unittest.TestCase):
	def setUp(self):
		self.lib = library.Library.createLibrary(':memory:')

	def tearDown(self):
		self.lib.disconnect()

	def test(self):
		pass
