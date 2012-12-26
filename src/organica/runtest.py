import unittest
import organica.tests.library, organica.tests.wildcard, organica.tests.formatstring
import organica.tests.objects, organica.tests.filters

def run():
    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.wildcard)
    # unittest.TextTestRunner().run(suite)

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.objects)
    # unittest.TextTestRunner().run(suite)

    suite = unittest.TestLoader().loadTestsFromModule(organica.tests.filters)
    unittest.TextTestRunner().run(suite)

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.formatstring)
    # unittest.TextTestRunner().run(suite)

    # suite = unittest.TestLoader().loadTestsFromModule(organica.tests.library)
    # unittest.TextTestRunner().run(suite)
