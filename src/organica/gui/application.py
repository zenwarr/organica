import os
import sys
import logging
import argparse
import threading
import locale

from PyQt4.QtGui import QApplication

from organica.utils.settings import globalSettings, globalQuickSettings, SettingsError
from organica.gui.actions import globalCommandManager
import organica.utils.constants as constants
from organica.gui.mainwin import globalMainWindow
from organica.utils.extend import globalPluginManager
from organica.gui.appsettings import doRegister


logger = logging.getLogger(__name__)


class InitError(Exception):
    pass


def runApplication():
    locale.setlocale(locale.LC_ALL, '')
    os.chdir(os.path.expanduser('~'))

    app = Application()
    app.startUp()
    return_code = app.exec_()
    app.shutdown()
    return return_code


class Application(QApplication):
    def __init__(self):
        QApplication.__init__(self, sys.argv)
        self.setApplicationName('Organica')
        self.setOrganizationName('zenwarr')
        self.setOrganizationDomain('http://github.org/zenwarr/organica')
        self.setApplicationVersion('0.0.1 pre-alpha')

    def startUp(self):
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

        doRegister()

        try:
            globalCommandManager().loadShortcutScheme()
        except Exception as err:
            logger.error('failed to read shortcuts scheme: ' + str(err))

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

        # parse arguments
        arguments = self.argparser.parse_args()

        if arguments.reset_settings:
            globalSettings().reset()
            globalQuickSettings().reset()
        else:
            try:
                globalSettings().load()
                globalQuickSettings().load()
            except SettingsError as err:
                logger.error(err)

        # init logging
        if globalSettings().get('log_file_name') is not None:
            logging.basicConfig(filename=globalSettings()['log_file_name'])
        else:
            logging.basicConfig()

        #todo: redirect standart io channels

        import organica.gui.genericprofile as genericprofile
        genericprofile.registerProfile()

        globalPluginManager().loadPlugins()

        self.mainWindow = globalMainWindow()
        self.mainWindow.show()

    def shutdown(self):
        globalPluginManager().unloadPlugins()
        globalCommandManager().saveShortcutScheme()
        globalSettings().save()
        globalQuickSettings().save()
        logging.shutdown()


_globalAppplication = None


def globalApplication():
    global _globalAppplication
    if _globalAppplication is None:
        _globalAppplication = Application()
    return _globalAppplication
