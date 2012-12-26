import sys, os, locale
import organica.utils.constants as constants
from organica.application import Application
from organica.gui.mainwin import MainWindow
from PyQt4.QtGui import QMainWindow
from PyQt4 import QtGui

def main():
    locale.setlocale(locale.LC_ALL, '')
    os.chdir(os.path.expanduser('~'))

    constants.app_dir = os.path.dirname(__file__)

    app = Application()
    app.startUp()
    return_code = app.exec_()
    app.shutdown()
    return return_code