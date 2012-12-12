import unittest
from organica.lib.objects import Identity, Object, Tag, TagClass, TagValue

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
