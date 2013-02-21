from organica.lib.formatstring import FormatString
from organica.lib.objects import Node
from organica.lib.library import Library
import unittest


class TestFormatString(unittest.TestCase):
    def test(self):
        lib = Library.createLibrary(':memory:')

        obj = Node('some_name')

        obj.link(lib.createTagClass('author'), 'Author name')
        obj.link(lib.createTagClass('pages_count'), 289)
        obj.link(lib.createTagClass('author'), 'Another author')
        obj.link(lib.createTagClass('author'), 'Third author')
        obj.link(lib.createTagClass('gentre'), 'Fiction')

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

        fs.template = '\\nnewline'
        self.assertEqual(fs.format(obj), '\nnewline')

        fs.template = 'authors are {author: default=unknown, max=2}'
        self.assertEqual(fs.format(obj), 'authors are Another author, Author name...')

        t = FormatString.buildFromTokens(fs.tokens)
        self.assertEqual(FormatString(t).format(obj), fs.format(obj))

        fs.template = '{@}'
        self.assertEqual(fs.format(obj), 'some_name')

        fs.template = '{pages_count: some_param}'  # should produce warning about unknown parameter
        self.assertEqual(fs.format(obj), '289')

        lib.disconnectDatabase()
