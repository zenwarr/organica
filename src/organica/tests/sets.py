import unittest
from organica.lib.sets import TagSet, NodeSet
from organica.lib.library import Library
from organica.lib.filters import TagQuery, NodeQuery, Wildcard


class TestTagSet(unittest.TestCase):
    def test(self):
        lib = Library.createLibrary(':memory:')

        author_class = lib.createTagClass('author')
        just_a_man_class = lib.createTagClass('just_a_man')
        pages_count_class = lib.createTagClass('pages_count_class')

        alice_node = lib.createNode('Alice in Wonderland')

        tagSet = TagSet(lib, TagQuery(tag_class=Wildcard('a*'), linked_with=alice_node))
        self.assertEqual(len(tagSet), 0)
        self.assertTrue(tagSet.lib is lib)

        author_carrol = lib.createTag(author_class, 'Lewis Carrol')
        author_dostoevsky = lib.createTag(author_class, 'Theodor Dostoevsky')

        self.assertEqual(len(tagSet), 0)

        alice_node.link(author_carrol)
        alice_node.flush(lib)

        self.assertEqual(len(tagSet), 1)
        self.assertTrue(author_carrol.identity in tagSet)

        author_carrol.tagClass = just_a_man_class
        author_carrol.flush()

        self.assertEqual(len(tagSet), 0)

        author_carrol.tagClass = author_class
        author_carrol.flush()

        self.assertEqual(len(tagSet), 1)

        lib.removeTag(author_carrol, remove_links=True)
        alice_node = lib.node(alice_node)
        self.assertEqual(len(tagSet), 0)

        tagSet.isPaused = True

        author_carrol = lib.createTag(author_class, 'Lewis Carrol')
        alice_node.link(author_carrol)
        alice_node.flush()

        self.assertEqual(len(tagSet), 0)
        tagSet.isPaused = False
        self.assertEqual(len(tagSet), 1)

        lib.disconnect()


class TestNodeSet(unittest.TestCase):
    def test(self):
        lib = Library.createLibrary(':memory:')

        node_set = NodeSet(lib, NodeQuery(tags=TagQuery(tag_class='author', text='Lewis Carrol'),
                                display_name=Wildcard('*alice*')))
        self.assertEqual(len(node_set), 0)

        alice_node = lib.createNode('Alice in Wonderland')
        alice_node.link(lib.createTagClass('author'), 'Lewis Carrol')
        alice_node.link(lib.createTagClass('pages_count'), 219)
        alice_node.flush()

        self.assertEqual(len(node_set), 1)
        self.assertTrue(alice_node.identity in node_set)

        # react on updating node
        alice_node.displayNameTemplate = 'Carrol book'
        alice_node.flush()

        self.assertEqual(len(node_set), 0)

        alice_node.displayNameTemplate = 'Alice in Wonderland'
        alice_node.flush()

        self.assertEqual(len(node_set), 1)

        # react on updating tag
        carrol_tag = lib.tags(TagQuery(tag_class='author', text='Lewis Carrol'))[0]
        carrol_tag.value = 'L. Carrol'
        carrol_tag.flush()

        self.assertEqual(len(node_set), 0)

        carrol_tag.value = 'Lewis Carrol'
        carrol_tag.flush()
        self.assertEqual(len(node_set), 1)

        # react on linking/unlinking tag
        alice_node.unlink(TagQuery(tag_class='author', text='Lewis Carrol'))
        alice_node.flush()

        self.assertEqual(len(node_set), 0)

        alice_node.link(lib.tagClass('author'), 'Lewis Carrol')
        alice_node.flush()

        self.assertEqual(len(node_set), 1)

        # pausing (freeze)
        node_set.isPaused = True

        alice_node.unlink(TagQuery(tag_class='author', text='Lewis Carrol'))
        alice_node.flush()

        self.assertEqual(len(node_set), 1)

        node_set.isPaused = False

        self.assertEqual(len(node_set), 0)

        alice_node.link(lib.tagClass('author'), 'Lewis Carrol')
        alice_node.flush()

        self.assertEqual(len(node_set), 1)

        alice_node.remove()
        self.assertEqual(len(node_set), 0)

        lib.disconnect()
