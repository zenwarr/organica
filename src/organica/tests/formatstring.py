from organica.lib.formatstring import FormatString
from organica.lib.objects import Node
import unittest


class TestFormatString(unittest.TestCase):
    def test(self):
        obj = Node('some_name')

        obj.link('author', 'Author name')
        obj.link('pages_count', 289)
        obj.link('author', 'Another author')
        obj.link('author', 'Third author')
        obj.link('gentre', 'Fiction')

        fs = FormatString()
        self.assertEqual(fs.format(obj), '')

        fs.template = 'formatted'
        self.assertEqual(fs.format(obj), 'formatted')

        fs.template = 'pages count is {pages_count}'
        self.assertEqual(fs.format(obj), 'pages count is 289')

        fs.template = 'title is {title}'
        self.assertEqual(fs.format(obj), 'title is ')

        fs.template = 'title is {title: default="unknown"}'
        self.assertEqual(fs.format(obj), 'title is unknown')

        fs.template = 'title is {title: default=unknown}'
        self.assertEqual(fs.format(obj), 'title is unknown')

