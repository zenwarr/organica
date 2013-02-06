import os
import logging
import json

from PyQt4.QtCore import QByteArray

import organica.utils.constants as constants
from organica.utils.lockable import Lockable


logger = logging.getLogger(__name__)


class SettingsError(Exception):
    pass


DEFAULT_SETTINGS_FILE = 'organica.conf'
DEFAULT_QUICK_SETTINGS_FILE = 'organica.qconf'


def _resolveConfigFilename(filename):
    return filename if os.path.isabs(filename) else os.path.join(constants.data_dir,
                                                                 filename)


class Settings(Lockable):
    """This class is used to access application settings. Settings are stored in
    human-readable (and human-editable) format (JSON). Use this class only
    with settings that are important to user. At example, window positions, list of last opened
    files, etc. should be processed with QuickSettings class.
    """

    def __init__(self, filename, strict_control=False):
        Lockable.__init__(self)
        self.filename = _resolveConfigFilename(filename)
        self.allSettings = {}
        self.registered = {}
        self.__strictControl = strict_control

    def load(self):
        """Reloads settings from configuration file. Throws SettingsError if fails.
        """

        with self.lock:
            self.allSettings = {}

            # if file does not exist, we just will not read settings (no exception)
            if not os.path.exists(self.filename):
                return

            try:
                with open(self.filename, 'rt') as f:
                    try:
                        settings = json.load(f)
                    except ValueError as err:
                        logger.error('error while parsing config file {0}: {1}'.format(self.filename, err))
                        settings = None

                    if settings is None:
                        return
                    elif not isinstance(settings, dict):
                        raise TypeError('invalid config file {0} format'.format(self.filename))

                    for key, value in settings.items():
                        if self.__strictControl and key not in self.registered:
                            logger.warn('unregistered setting in config file {0}: {1}' \
                                        .format(self.filename, key))
                        else:
                            self.allSettings[key] = value
            except Exception as err:
                raise SettingsError('failed to load settings: {0}'.format(err))

    def save(self, keep_unregistered=True):
        """Store all settings into file. If :keep_unregistered: is True, it
        will keep settings that are not registered at the moment of saving.
        If target file does not exist, it will be created as well as required
        directories. Raises SettingsError if fails.
        """

        with self.lock:
            try:
                os.makedirs(os.path.dirname(self.filename), exist_ok=True)
                with open(self.filename, 'w+t') as f:
                    settings = self.allSettings

                    if keep_unregistered:
                        try:
                            saved_settings = json.load(f)
                        except ValueError:
                            saved_settings = None

                        if saved_settings is not None and isinstance(saved_settings, dict):
                            for key, value in saved_settings:
                                if key not in self.registered:
                                    settings[key] = saved_settings[key]

                    json.dump(settings, f, ensure_ascii=False, indent=4)
            except Exception as err:
                raise SettingsError('failed to save settings: {0}'.format(err))

    def reset(self):
        """Reset all settings to defaults.
        """

        with self.lock:
            if os.path.exists(self.filename):
                os.remove(self.filename)
            self.allSettings = {}

    def resetSetting(self, setting_name):
        with self.lock:
            if self.__strictControl and setting_name not in self.registered:
                raise SettingsError('writing unregistered setting %s' % setting_name)
            del self.allSettings[setting_name]

    def get(self, setting_name):
        with self.lock:
            if setting_name in self.allSettings:
                return self.allSettings[setting_name]
            elif setting_name in self.registered:
                return self.registered[setting_name]
            elif self.__strictControl:
                raise SettingsError('reading unregistered setting %s' % setting_name)
            else:
                return None

    def defaultValue(self, setting_name):
        with self.lock:
            if setting_name in self.registered:
                return self.registered[setting_name]
            elif self.__strictControl:
                raise SettingsError('reading unregistered setting %s' % setting_name)
            else:
                return None

    def set(self, setting_name, value):
        with self.lock:
            if self.__strictControl and setting_name not in self.registered:
                raise SettingsError('writing unregistered setting %s' % setting_name)

            if setting_name in self.registered and self.registered[setting_name] == value:
                del self.allSettings[setting_name]
            else:
                self.allSettings[setting_name] = value

    def register(self, setting_name, default_value=None):
        """Register setting with specified name and default value.
        """

        with self.lock:
            if setting_name not in self.registered:
                self.registered[setting_name] = default_value
            else:
                raise SettingsError('cannot register setting {0}: another one registed with this name' \
                                   .format(setting_name))

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        self.set(key, value)

    def __delitem__(self, key):
        self.resetSetting(key)


_globalSettings = None
_globalQuickSettings = None


def globalSettings():
    global _globalSettings
    if _globalSettings is None:
        _globalSettings = Settings(DEFAULT_SETTINGS_FILE, strict_control=True)
    return _globalSettings


def globalQuickSettings():
    global _globalQuickSettings
    if _globalQuickSettings is None:
        _globalQuickSettings = Settings(DEFAULT_QUICK_SETTINGS_FILE)
    return _globalQuickSettings
