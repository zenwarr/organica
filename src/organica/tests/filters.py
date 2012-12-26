import unittest
from organica.lib.objects import Object, Tag, TagClass, TagValue, Identity
from organica.lib.filters import TagFilter, ObjectFilter, Wildcard
from organica.lib.library import Library
from organica.lib.locator import Locator
from PyQt4.QtCore import QUrl

class TestFilters(unittest.TestCase):
    def test(self):
        lib = Library.createLibrary(':memory:')

        author_carrol = Tag('author', 'Lewis Carrol')
        author_shakespeare = Tag('author', 'Shakespeare')
        page_count = Tag('page_count', 489)

        f = TagFilter().tagClass('author')
        self.assertTrue(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(),
                        "class_id in (select id from tag_classes where name = 'author')")

        f = TagFilter().tagClass(Wildcard('*r'))
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(),
                        "class_id in (select id from tag_classes where name like '%r' escape '!')")

        f = TagFilter().tagClass(TagClass())
        self.assertFalse(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), '1 = 2')

        f = TagFilter().tagClass(TagClass('author'))
        self.assertTrue(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "class_id in (select id from tag_classes where name = 'author')")

        f = TagFilter().identity(author_carrol)
        self.assertFalse(author_carrol.passes(f)) # unflushed yet
        self.assertFalse(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "1 = 2")

        author_carrol.flush(lib)

        f = TagFilter().identity(author_carrol)
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "id = {0}".format(author_carrol.id))

        f = TagFilter().number(page_count.value.number)
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = {1}".format(TagValue.TYPE_NUMBER,
                         page_count.value.number))
        self.assertTrue(page_count.passes(f))
        self.assertFalse(author_carrol.passes(f))
        page_count.value.number = 1000
        self.assertFalse(page_count.passes(f))

        f = TagFilter().number(1000, '>')
        self.assertFalse(page_count.passes(f))
        page_count.value.number = 1200
        self.assertTrue(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value > 1000".format(TagValue.TYPE_NUMBER))

        f = TagFilter().text('Shakespeare')
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'Shakespeare' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagFilter().text('shakespeare')
        self.assertTrue(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'shakespeare' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        author_shakespeare.value.text = 'Шекспир'

        f = TagFilter().text(author_shakespeare.value.text)
        self.assertTrue(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'Шекспир' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagFilter().text('шекспир')
        self.assertTrue(author_shakespeare.passes(f))

        author_shakespeare.value.text = 'Shakespeare'

        f = TagFilter().text(Wildcard('L*'))
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value like 'L%' escape '!' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagFilter().text(Wildcard('*'))
        self.assertTrue(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value like '%' escape '!' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagFilter().text('*')
        self.assertFalse(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = '*' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        loc = Locator('file://localhost/home/username/file.txt')
        locator_file = Tag('file', loc)
        locator_website = Tag('file', Locator('https://google.com/'))

        f = TagFilter().locator(loc)
        self.assertTrue(locator_file.passes(f))
        self.assertFalse(locator_website.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = '{1}'".format(TagValue.TYPE_LOCATOR,
                         loc.databaseForm()))

        obj1, obj2 = Object('some_object'), Object('another_object')
        obj1.flush(lib)
        obj2.flush(lib)

        tag_obj1 = Tag('link', obj1)
        tag_obj2 = Tag('link', obj2)

        f = TagFilter().objectReference(obj1)
        self.assertTrue(tag_obj1.passes(f))
        self.assertFalse(tag_obj2.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = {1}".format(TagValue.TYPE_OBJECT_REFERENCE,
                         obj1.id))

        f = TagFilter().objectReference(Identity())
        self.assertFalse(tag_obj1.passes(f))
        self.assertEqual(f.generateSqlWhere(), "1 = 2")

        noneTag = Tag('none', None)
        f = TagFilter().none()
        self.assertTrue(noneTag.passes(f))
        self.assertFalse(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0}".format(TagValue.TYPE_NONE))

        f = TagFilter().valueType(TagValue.TYPE_TEXT)
        self.assertTrue(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(noneTag.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0}".format(TagValue.TYPE_TEXT))

        obj = Object('Alice in Wonderland')
        obj.link(author_carrol)
        obj.link(page_count)
        obj.flush(lib)

        f = TagFilter().unused()
        self.assertEqual(f.generateSqlWhere(), "id not in (select distinct tag_id from links)")
        self.assertFalse(author_carrol.passes(f))
        author_carrol.flush(lib)
        obj.unlink(author_carrol.identity)
        self.assertFalse(author_carrol.passes(f))
        obj.flush()
        self.assertTrue(author_carrol.passes(f))

        self.assertFalse(author_shakespeare.passes(f)) # as tag is unflushed
        author_shakespeare.flush(lib)
        self.assertTrue(author_shakespeare.passes(f)) # tag became flushed
        obj1.link(author_shakespeare)
        self.assertTrue(author_shakespeare.passes(f)) # tag is linked to object, but it is not
                                                      # reflected in database yet
        obj1.flush(lib)
        self.assertFalse(author_shakespeare.passes(f))

        f = TagFilter().value('Lewis Carrol')
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'Lewis Carrol' collate strict_nocase" \
                             .format(TagValue.TYPE_TEXT))
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))

        f = TagFilter().linkedWith(obj)
        self.assertEqual(f.generateSqlWhere(), "id in (select tag_id from links where object_id = {0})" \
                         .format(obj.id))
        self.assertFalse(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))
        obj.link(author_carrol)
        obj.flush()
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))
        obj.unlink(author_carrol)
        obj.flush()
        self.assertFalse(author_carrol.passes(f))

        f = TagFilter().linkedWith(obj1).tagClass('author')
        self.assertEqual(f.generateSqlWhere(), ("(id in (select tag_id from links where object_id = {0})) and " \
                         + "(class_id in (select id from tag_classes where name = 'author'))").format(obj1.id))
        self.assertFalse(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))

        f = TagFilter().linkedWith(obj1) & TagFilter().valueType(TagValue.TYPE_NUMBER)
        self.assertEqual(f.generateSqlWhere(), ("(id in (select tag_id from links where object_id = {0})) and " \
                         + "(value_type = {1})").format(obj1.id, TagValue.TYPE_NUMBER))
        self.assertFalse(author_carrol.passes(f))

        f = TagFilter().linkedWith(obj1) | TagFilter().valueType(TagValue.TYPE_NUMBER)
        self.assertEqual(f.generateSqlWhere(), ("(id in (select tag_id from links where object_id = {0})) or " \
                         + "(value_type = {1})").format(obj1.id, TagValue.TYPE_NUMBER))
        self.assertFalse(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertTrue(page_count.passes(f))

        f = ~TagFilter().valueType(TagValue.TYPE_TEXT)
        self.assertEqual(f.generateSqlWhere(), "not (value_type = {0})".format(TagValue.TYPE_TEXT))
        self.assertTrue(page_count.passes(f))
        self.assertFalse(author_carrol.passes(f))

        f = ObjectFilter().displayName('Alice in Wonderland')
        self.assertEqual(f.generateSqlWhere(), "display_name = 'Alice in Wonderland'")
        self.assertTrue(obj.passes(f))
        self.assertFalse(obj1.passes(f))

        f = ObjectFilter().displayName(Wildcard('*in*'))
        self.assertEqual(f.generateSqlWhere(), "display_name like '%in%' escape '!'")
        self.assertTrue(obj.passes(f))
        self.assertFalse(obj1.passes(f))

        f = ObjectFilter().identity(obj)
        self.assertEqual(f.generateSqlWhere(), "id = {0}".format(obj.id))
        self.assertTrue(obj.passes(f))
        self.assertFalse(obj1.passes(f))

        obj_alice = Object('Alice in Wonderland')
        obj_alice.link('author', 'Lewis Carrol')
        obj_alice.link('gentre', 'Fiction')
        obj_alice.link('year', '1888')
        obj_alice.flush(lib)

        obj_unknown_book = Object('Untitled')
        obj_unknown_book.flush(lib)

        obj_another_book = Object('Another book')
        obj_another_book.link('author', 'Another author')
        obj_another_book.flush(lib)

        obj_unflushed = Object('Unflushed')

        lib.dump()

        f = ObjectFilter().tags(TagFilter().identity(author_carrol))
        self.assertEqual(f.generateSqlWhere(), ("id in (select object_id " \
                         + "from links where tag_id in (select id from tags " \
                         + "where id = {0}))").format(author_carrol.id))
        self.assertTrue(obj_alice.passes(f))
        self.assertFalse(obj_unknown_book.passes(f))
        self.assertFalse(obj_another_book.passes(f))

        f = ObjectFilter().withoutTags()
        self.assertEqual(f.generateSqlWhere(), "id not id (select distinct object_id from links)")
        self.assertFalse(obj_alice.passes(f))
        self.assertFalse(obj_another_book.passes(f))
        self.assertFalse(obj_unknown_book.passes(f))
        self.assertFalse(obj_unflushed.passes(f))
