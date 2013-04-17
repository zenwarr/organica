import os
import sys
import logging
import argparse
import threading
import locale

from PyQt4.QtCore import QTextCodec
from PyQt4.QtGui import QApplication

from organica.utils.settings import globalSettings, globalQuickSettings, SettingsError
import organica.utils.settings as settings
from organica.gui.actions import globalCommandManager
import organica.utils.constants as constants
from organica.gui.mainwin import globalMainWindow
from organica.utils.extend import globalPluginManager
import organica.gui.appsettings as appsettings
import organica.generic.extension as generic_extension


logging.basicConfig()
logger = logging.getLogger(__name__)


class InitError(Exception):
    pass


def runApplication():
    locale.setlocale(locale.LC_ALL, '')
    os.chdir(os.path.expanduser('~'))

    app = globalApplication()
    try:
        app.startUp()
    except InitError as err:
        print('application failed to initialize: {0}'.format(err))
        return -1
    else:
        return_code = app.exec_()
        app.shutdown()
        return return_code


class Application(QApplication):
    def __init__(self):
        QApplication.__init__(self, sys.argv)
        self.setApplicationName('Organica')
        self.setOrganizationName('zenwarr')
        self.setOrganizationDomain('http://github.org/zenwarr/organica')
        self.setApplicationVersion('0.0.1 indev')
        self.argparser = None
        self.arguments = object()

    def startUp(self):
        constants.gui_thread = threading.current_thread()

        QTextCodec.setCodecForCStrings(QTextCodec.codecForName('UTF-8'))

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
                    msg = 'application is running in portable mode, but has no access to data directory %s'.format(data_dir)
                    raise InitError(msg)
            elif not os.access(data_dir, os.R_OK | os.W_OK):
                # we should have at least read-write access to data directory.
                msg = 'application is running in portable mode, but has no enough rights for accessing data directory %s'.format(data_dir)
                raise InitError(msg)
            else:
                constants.is_portable = True

        print('constants.is_portable = {0}'.format(constants.is_portable))

        # set data directory
        if constants.is_portable:
            constants.data_dir = os.path.join(constants.app_dir, "data")
        elif sys.platform.startswith('win32'):
            constants.data_dir = os.path.expanduser('~/Application Data/Organica')
        elif sys.platform.startswith('darwin'):
            constants.data_dir = os.path.expanduser('~/Library/Application Support/Organica')
        else:
            constants.data_dir = os.path.expanduser('~/.organica')

        print('constants.data_dir = {0}'.format(constants.data_dir))

        settings.defaultSettingsDirectory = constants.data_dir
        settings.defaultSettingsFilename = 'organica.conf'
        settings.defaultQuickSettingsFilename = 'organica.qconf'
        settings.warningOutputRoutine = logger.warn

        appsettings.doRegister()

        # initialize argument parser. We can use it later, when another instance delivers args to us
        self.argparser = argparse.ArgumentParser(prog=self.applicationName())
        self.argparser.add_argument('-v', '--version',
                                    action='version',
                                    version='Organica ' + self.applicationVersion(),
                                    help='show application version and exit')
        self.argparser.add_argument('files', nargs='?')
        self.argparser.add_argument('--reset-settings', dest='resetSettings',
                                    action='store_true',
                                    help='reset application settings to defaults')
        self.argparser.add_argument('--disable-plugins', dest='disablePlugins', action='store_true',
                                    help='do not load any plugins')

        # parse arguments
        self.arguments = self.argparser.parse_args()

        if self.arguments.resetSettings:
            globalSettings().reset()
            globalQuickSettings().reset()
        else:
            try:
                globalSettings().load()
            except SettingsError as err:
                logger.error(err)

            try:
                globalQuickSettings().load()
            except SettingsError as err:
                logger.error(err)

        try:
            globalCommandManager().loadShortcutScheme()
        except Exception as err:
            print('failed to read shortcuts scheme: ' + str(err))

        generic_extension.register()

        globalPluginManager().loadPlugins()

        self.mainWindow = globalMainWindow()
        self.mainWindow.show()

    def shutdown(self):
        globalCommandManager().saveShortcutScheme()
        globalSettings().save()
        globalQuickSettings().save()
        globalPluginManager().unloadPlugins()
        logging.shutdown()


_globalAppplication = None


def globalApplication():
    global _globalAppplication
    if _globalAppplication is None:
        _globalAppplication = Application()
    return _globalAppplication
