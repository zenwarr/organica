import unittest
from organica.lib.objects import Node, Tag, TagValue, Identity
from organica.lib.filters import TagQuery, NodeQuery, Wildcard
from organica.lib.library import Library
from organica.lib.locator import Locator


class TestFilters(unittest.TestCase):
    def test(self):
        lib = Library.createLibrary(':memory:')

        author_class = lib.createTagClass('author')
        page_count_class = lib.createTagClass('page_count')

        author_carrol = Tag(author_class, 'Lewis Carrol')
        author_shakespeare = Tag(author_class, 'Shakespeare')
        page_count = Tag(page_count_class, 489)

        f = TagQuery(tag_class='author')
        self.assertTrue(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(),
                        "class_id in (select id from tag_classes where name = 'author')")

        f = TagQuery(tag_class=Wildcard('*r'))
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(),
                        "class_id in (select id from tag_classes where name like '%r' escape '!')")

        f = TagQuery(tag_class=author_class)
        self.assertTrue(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "class_id = {0}".format(author_class.id))

        f = TagQuery(identity=author_carrol)
        self.assertFalse(author_carrol.passes(f))  # unflushed yet
        self.assertFalse(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "1 = 2")

        author_carrol.flush(lib)

        f = TagQuery(identity=author_carrol)
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "id = {0}".format(author_carrol.id))

        f = TagQuery(number=page_count.value.number)
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = {1}" \
                         .format(TagValue.TYPE_NUMBER, page_count.value.number))
        self.assertTrue(page_count.passes(f))
        self.assertFalse(author_carrol.passes(f))
        page_count.value.number = 1000
        self.assertFalse(page_count.passes(f))

        f = TagQuery(number_gt=1000)
        self.assertFalse(page_count.passes(f))
        page_count.value.number = 1200
        self.assertTrue(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value > 1000".format(TagValue.TYPE_NUMBER))

        f = TagQuery(text='Shakespeare')
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'Shakespeare' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagQuery(text='shakespeare')
        self.assertTrue(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'shakespeare' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        author_shakespeare.value.text = 'Шекспир'

        f = TagQuery(text=author_shakespeare.value.text)
        self.assertTrue(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'Шекспир' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagQuery(text='шекспир')
        self.assertTrue(author_shakespeare.passes(f))

        author_shakespeare.value.text = 'Shakespeare'

        f = TagQuery(text=Wildcard('L*'))
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value like 'L%' escape '!' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagQuery(text=Wildcard('*'))
        self.assertTrue(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value like '%' escape '!' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        f = TagQuery(text='*')
        self.assertFalse(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = '*' collate strict_nocase" \
                         .format(TagValue.TYPE_TEXT))

        loc = Locator('file://localhost/home/username/file.txt')
        locator_file = Tag(lib.createTagClass('file'), loc)
        locator_website = Tag(lib.createTagClass('file'), Locator('https://google.com/'))

        f = TagQuery(locator=loc)
        self.assertTrue(locator_file.passes(f))
        self.assertFalse(locator_website.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = '{1}'".format(TagValue.TYPE_LOCATOR,
                         loc.databaseForm))

        obj1, obj2 = Node('some_object'), Node('another_object')
        obj1.flush(lib)
        obj2.flush(lib)

        tag_obj1 = Tag(lib.createTagClass('link'), obj1)
        tag_obj2 = Tag(lib.createTagClass('link'), obj2)

        f = TagQuery(node_ref=obj1)
        self.assertTrue(tag_obj1.passes(f))
        self.assertFalse(tag_obj2.passes(f))
        self.assertFalse(page_count.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = {1}".format(TagValue.TYPE_NODE_REFERENCE,
                         obj1.id))

        f = TagQuery(node_ref=Identity())
        self.assertFalse(tag_obj1.passes(f))
        self.assertEqual(f.qeval(), 0)

        noneTag = Tag(lib.createTagClass('none'), None)
        f = TagQuery(none=None)
        self.assertTrue(noneTag.passes(f))
        self.assertFalse(author_carrol.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0}".format(TagValue.TYPE_NONE))

        f = TagQuery(value_type=TagValue.TYPE_TEXT)
        self.assertTrue(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertFalse(noneTag.passes(f))
        self.assertEqual(f.generateSqlWhere(), "value_type = {0}".format(TagValue.TYPE_TEXT))

        obj = Node('Alice in Wonderland')
        obj.link(author_carrol)
        obj.link(page_count)
        obj.flush(lib)

        f = TagQuery(unused=None)
        self.assertEqual(f.generateSqlWhere(), "id not in (select distinct tag_id from links)")
        self.assertFalse(author_carrol.passes(f))
        obj.unlink(author_carrol.identity)
        self.assertFalse(author_carrol.passes(f))
        obj.flush()
        self.assertTrue(author_carrol.passes(f))

        self.assertFalse(author_shakespeare.passes(f))  # as tag is unflushed
        author_shakespeare.flush(lib)
        self.assertTrue(author_shakespeare.passes(f))  # tag became flushed
        obj1.link(author_shakespeare)
        self.assertTrue(author_shakespeare.passes(f))  # tag is linked to object, but this fact is not
                                                       # reflected in database yet
        obj1.flush(lib)
        self.assertFalse(author_shakespeare.passes(f))

        f = TagQuery(value='Lewis Carrol')
        self.assertEqual(f.generateSqlWhere(), "value_type = {0} and value = 'Lewis Carrol' collate strict_nocase" \
                             .format(TagValue.TYPE_TEXT))
        self.assertTrue(author_carrol.passes(f))
        self.assertFalse(author_shakespeare.passes(f))

        f = TagQuery(linked_with=obj)
        self.assertEqual(f.generateSqlWhere(), "id in (select tag_id from links where node_id = {0})" \
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

        f = TagQuery(linked_with=obj1, tag_class='author')
        self.assertFalse(author_carrol.id == author_shakespeare.id)
        self.assertFalse(lib.node(obj1).testTag(author_carrol))
        self.assertFalse(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))

        f = TagQuery(linked_with=obj1) & TagQuery(value_type=TagValue.TYPE_NUMBER)
        self.assertEqual(f.generateSqlWhere(), ("(id in (select tag_id from links where node_id = {0})) and " \
                         + "(value_type = {1})").format(obj1.id, TagValue.TYPE_NUMBER))
        self.assertFalse(author_carrol.passes(f))

        f = TagQuery(linked_with=obj1) | TagQuery(value_type=TagValue.TYPE_NUMBER)
        self.assertEqual(f.generateSqlWhere(), ("(id in (select tag_id from links where node_id = {0})) or " \
                         + "(value_type = {1})").format(obj1.id, TagValue.TYPE_NUMBER))
        self.assertFalse(author_carrol.passes(f))
        self.assertTrue(author_shakespeare.passes(f))
        self.assertTrue(page_count.passes(f))

        f = ~TagQuery(value_type=TagValue.TYPE_TEXT)
        self.assertEqual(f.generateSqlWhere(), "not (value_type = {0})".format(TagValue.TYPE_TEXT))
        self.assertTrue(page_count.passes(f))
        self.assertFalse(author_carrol.passes(f))

        f = NodeQuery(display_name='Alice in Wonderland')
        self.assertEqual(f.generateSqlWhere(), "display_name = 'Alice in Wonderland'")
        self.assertTrue(obj.passes(f))
        self.assertFalse(obj1.passes(f))

        f = NodeQuery(display_name=Wildcard('*in*'))
        self.assertEqual(f.generateSqlWhere(), "display_name like '%in%' escape '!'")
        self.assertTrue(obj.passes(f))
        self.assertFalse(obj1.passes(f))

        f = NodeQuery(identity=obj)
        self.assertEqual(f.generateSqlWhere(), "id = {0}".format(obj.id))
        self.assertTrue(obj.passes(f))
        self.assertFalse(obj1.passes(f))

        obj_alice = Node('Alice in Wonderland')
        obj_alice.link(lib.createTagClass('author'), 'Lewis Carrol')
        obj_alice.link(lib.createTagClass('gentre'), 'Fiction')
        obj_alice.link(lib.createTagClass('year'), '1888')
        obj_alice.flush(lib)

        obj_unknown_book = Node('Untitled')
        obj_unknown_book.flush(lib)

        obj_another_book = Node('Another book')
        obj_another_book.link(lib.createTagClass('author'), 'Another author')
        obj_another_book.flush(lib)

        obj_unflushed = Node('Unflushed')

        f = NodeQuery(tags=TagQuery(identity=author_carrol))
        self.assertEqual(f.generateSqlWhere(), ("id in (select node_id " \
                         + "from links where tag_id in (select id from tags " \
                         + "where id = {0}))").format(author_carrol.id))
        self.assertTrue(obj_alice.passes(f))
        self.assertFalse(obj_unknown_book.passes(f))
        self.assertFalse(obj_another_book.passes(f))

        f = NodeQuery(no_tags=None)
        self.assertEqual(f.generateSqlWhere(), "id not in (select distinct node_id from links)")
        self.assertFalse(obj_alice.passes(f))
        self.assertFalse(obj_another_book.passes(f))
        self.assertTrue(obj_unknown_book.passes(f))
        self.assertTrue(obj_unflushed.passes(f))

        # test hinting of filters

        f = TagQuery(tag_class='author')
        f.hint = 'my_hint'
        self.assertEqual(f.qeval(), -1)
        f.disableHinted('my_hint')
        self.assertEqual(f.qeval(), 1)

        lib.disconnect()
