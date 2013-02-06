import unittest

from organica.lib.tagsmodel import TagsModel
from organica.tests.samplelib import buildSample


class TestTagsModel(unittest.TestCase):
    def test(self):
        lib = buildSample()
        model = TagsModel(lib)
        model.hierarchy = ['gentre', 'author']

        self.assertEqual(model.hierarchy, ['gentre', 'author'])

        self.assertEqual(model.rowCount(), 3)

        another_book = lib.createNode('Another book')
        another_book.link(lib.createTagClass('gentre'), 'Brand new gentre')
        another_book.flush(lib)

        self.assertEqual(model.rowCount(), 4)

        values = [model.data(model.index(x, 1)) for x in range(4)]
        self.assertEqual(sorted(values), ['Brand new gentre', 'Fiction', 'Novel', 'Tragedy'])

        lib.tag('gentre', 'Novel').remove(remove_links=True)
        self.assertEqual(model.rowCount(), 3)

        values = [model.data(model.index(x, 1)) for x in range(3)]
        self.assertEqual(sorted(values), ['Brand new gentre', 'Fiction', 'Tragedy'])

        lib.disconnect()
