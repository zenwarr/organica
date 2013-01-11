import os
import sys
import logging
import argparse
import threading

from organica.utils.settings import Settings
from organica.gui.actions import globalCommandManager
import organica.utils.constants as constants
from organica.gui.mainwin import MainWindow
from PyQt4 import QtGui


logger = logging.getLogger(__name__)


class InitError(Exception):
    def __init__(self, desc=''):
        Exception.__init__(self, desc)


class Application(QtGui.QApplication):
    def __init__(self):
        QtGui.QApplication.__init__(self, sys.argv)
        self.setApplicationName('Organica')
        self.setOrganizationName('zenwarr')
        self.setOrganizationDomain('http://github.org/zenwarr/organica')
        self.setApplicationVersion('0.0.1 pre-alpha')

        logging.basicConfig()

        constants.gui_thread = threading.current_thread()

        # detect if we are running in portable mode. Portable mode is turning off
        # if installation.mark file exist in application directory.
        if os.path.exists(os.path.join(constants.app_dir, 'installation.mark')):
            constants.is_portable = False
        else:
            # check accessibility of data directory. In portable mode, all data are
            # stored under '{ApplicationInstall}/data'
            data_dir = os.path.join(constants.app_dir, 'data')
            if not os.path.exists(data_dir):
                try:
                    os.mkdir(data_dir)
                    constants.is_portable = True
                except OSError:
                    logger.error('application is running in portable mode, but has no access to data directory %s',
                                 data_dir)
                    raise InitError()
            elif not os.access(data_dir, os.R_OK | os.W_OK):
                # we should have at least read-write access to data directory.
                logger.error('application is running in portable mode, but has no enough rights for accessing data directory %s',
                             data_dir)
                raise InitError()
            else:
                constants.is_portable = True

        logger.debug('constants.is_portable = {0}'.format(constants.is_portable))

        # set data directory
        if constants.is_portable:
            constants.data_dir = os.path.join(constants.app_dir, "data")
        elif sys.platform.startswith('win32'):
            constants.data_dir = os.path.expanduser('~/Application Data/Organica')
        elif sys.platform.startswith('darwin'):
            constants.data_dir = os.path.expanduser('~/Library/Application Support/Organica')
        else:
            constants.data_dir = os.path.expanduser('~/.config/organica')

        logger.debug('constants.data_dir = {0}'.format(constants.data_dir))

        self.__registerSettings()

        globalCommandManager().loadShortcutScheme()

        # initialize argument parser. We can use it later, when another instance delivers args to us
        self.argparser = argparse.ArgumentParser(prog=self.applicationName())
        self.argparser.add_argument('-v', '--version',
                                action='version',
                                version='Organica ' + self.applicationVersion(),
                                help='show application version and exit')
        self.argparser.add_argument('files', nargs='?')
        self.argparser.add_argument('--reset-settings', dest='reset_settings',
                                    action='store_true',
                                    help='reset application settings to defaults')

    def startUp(self):
        # parse arguments
        arguments = self.argparser.parse_args()

        if arguments.reset_settings:
            Settings().reset()
        else:
            Settings().load()

        # init logging
        if Settings().get('log_file_name') != None:
            logging.basicConfig(filename=Settings().get('log_file_name'))
        else:
            logging.basicConfig()

        #todo: redirect standart io channels

        self.mainWindow = MainWindow()
        self.mainWindow.show()

    def shutdown(self):
        globalCommandManager().saveShortcutScheme()
        Settings().save()
        logging.shutdown()

    def __registerSettings(self):
        all_settings = (
            ('log_file_name', None),
        )

        s = Settings()
        for k, v in all_settings:
            s.register(k, v)
