import unittest
import organica.utils.constants as constants
import organica.tests.library
import organica.tests.wildcard
import organica.tests.formatstring
import organica.tests.objects
import organica.tests.filters
import organica.tests.sets


def run():
    constants.disable_set_queued_connections = True

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.wildcard)
    # unittest.TextTestRunner().run(suite)

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.objects)
    # unittest.TextTestRunner().run(suite)

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.filters)
    # unittest.TextTestRunner().run(suite)

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.formatstring)
    # unittest.TextTestRunner().run(suite)

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.library)
    # unittest.TextTestRunner().run(suite)

    suite = unittest.TestLoader().loadTestsFromModule(organica.tests.sets)
    unittest.TextTestRunner().run(suite)
