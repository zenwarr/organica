import unittest
import organica.tests.library

def run():
	suite = unittest.TestLoader().loadTestsFromModule(organica.tests.library)
	unittest.TextTestRunner().run(suite)
