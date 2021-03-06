import unittest

import organica.utils.constants as constants
import organica.tests.library
import organica.tests.wildcard
import organica.tests.formatstring
import organica.tests.objects
import organica.tests.filters
import organica.tests.sets
import organica.tests.extend
import organica.tests.operations
import organica.tests.tagsmodel
import organica.tests.objectsmodel


def run():
    constants.disable_set_queued_connections = True
    constants.test_run = True

    module_list = (
                    organica.tests.wildcard,
                    organica.tests.objects,
                    organica.tests.filters,
                    organica.tests.formatstring,
                    organica.tests.library,
                    organica.tests.sets,
                    organica.tests.extend,
                    organica.tests.operations,
                    organica.tests.tagsmodel,
                    organica.tests.objectsmodel,
                   )

    for module in module_list:
        suite = unittest.TestLoader().loadTestsFromModule(module)
        unittest.TextTestRunner().run(suite)


if __name__ == '__main__':
    run()
