import unittest
from organica.lib.objectsmodel import ObjectsModel
from organica.tests.samplelib import buildSample


class TestObjectsModel(unittest.TestCase):
    def test(self):
        lib = buildSample()

        model = ObjectsModel(lib)
        # should show all objects

        self.assertEqual(model.rowCount(), 4)
