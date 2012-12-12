import unittest
from organica.lib.filters import Wildcard

class WildcardTest(unittest.TestCase):
    def test(self):
        w = Wildcard('author')
        self.assertEqual(w, 'author')
        self.assertNotEqual(w, 'authors')
        self.assertNotEqual(w, 'not_authors')

        w = Wildcard('au*')
        self.assertEqual(w, 'author')
        self.assertEqual(w, 'auth')
        self.assertNotEqual(w, 'a')
        self.assertNotEqual(w, '')

        w = Wildcard('a?thor')
        self.assertEqual(w, 'author')
        self.assertEqual(w, 'anthor')
        self.assertNotEqual(w, 'auuuthor')

        w = Wildcard()
        self.assertNotEqual(w, 'author')
        self.assertEqual(w, '')

        w = Wildcard('[a-Z]auth*')
        self.assertEqual(w, '[a-Z]author')
        self.assertNotEqual(w, 'aauth')
