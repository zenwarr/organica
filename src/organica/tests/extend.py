import unittest
import uuid
from organica.utils.extend import ObjectPool


class DummyExtObject(object):
    def __init__(self, group='', ext_uuid=None):
        self.extensionUuid = ext_uuid or uuid.uuid4()
        self.group = group


class TestObjectPool(unittest.TestCase):
    def test(self):
        pool = ObjectPool()
        self.assertEqual(len(pool), 0)

        ext1_uuid = uuid.uuid4()
        obj1 = DummyExtObject('main', ext1_uuid)
        obj2 = DummyExtObject('another_group', ext1_uuid)
        obj3 = DummyExtObject('another_group', ext1_uuid)
        ext2_uuid = uuid.uuid4()
        obj4 = DummyExtObject('another_group', ext2_uuid)

        pool.add(obj1)
        self.assertEqual(len(pool), 1)
        self.assertTrue(obj1 in pool)
        self.assertEqual(pool.objects('main'), [obj1])

        pool.add((obj2, obj3, obj4))
        self.assertEqual(len(pool), 4)

        pool.removeObjects(lambda x: x.group == 'another_group')
        self.assertEqual(len(pool), 1)
        self.assertEqual(pool.objects(), [obj1])

        for obj in pool:
            print(obj.group)
