import os
import logging
import json

import organica.utils.constants as constants
from organica.utils.lockable import Lockable


logger = logging.getLogger(__name__)


class SettingsError(Exception):
    pass


DEFAULT_SETTINGS_FILE = 'organica.conf'
DEFAULT_QUICK_SETTINGS_FILE = 'organica.qconf'


class Settings(Lockable):
    """This class is used to access application settings. Settings are stored in
    human-readable (and human-editable) format (JSON).
    Class can optionally allow only limited set of settings to be saved by registering
    name for each settings. This feature also allows application to set default values for
    each registered setting. If strict_control argument passed to constructor is False (default), object
    will not control keys and will not support default values for settings.
    You can access values with dictionary-like syntax (__getitem__, __setitem__, __delitem__)
    """

    def __init__(self, filename, strict_control=False):
        Lockable.__init__(self)
        self.__filename = filename
        self.allSettings = {}
        self.registered = {}
        self.__strictControl = strict_control

    @property
    def filename(self):
        return self.__filename if os.path.isabs(self.__filename) else os.path.join(constants.data_dir, self.__filename)

    def load(self):
        """Reloads settings from configuration file. If settings filename does not exist or empty, no error raised
        (assuming that all settings has default values). But if file exists but not accessible, SettingsError
        will be raised. Invalid file structure also causes SettingsError to be raised.
        Stored keys that are not registered will cause logging warning message, but it is not critical error (due
        to compatibility with future versions and plugins). Unregistered settings are placed in allSettings dictionary.
        """

        with self.lock:
            self.allSettings = {}

            if not os.path.exists(self.filename):
                return

            try:
                with open(self.filename, 'rt') as f:
                    # test file size, if zero - do nothing
                    if not os.fstat(f.fileno()).st_size:
                        return

                    try:
                        settings = json.load(f)
                    except ValueError as err:
                        raise SettingsError('error while parsing config file {0}: {1}'.format(self.filename, err))

                    if not isinstance(settings, dict):
                        raise SettingsError('invalid config file {0} format'.format(self.filename))

                    for key, value in settings.items():
                        if self.__strictControl and key not in self.registered:
                            logger.warn('unregistered setting in config file {0}: {1}'.format(self.filename, key))
                        self.allSettings[key] = value
            except Exception as err:
                raise SettingsError('failed to load settings: {0}'.format(err))

    def save(self, keep_unregistered=True):
        """Store all settings into file.
        If :keep_unregistered: is True, settings that present in target file but not in :registered: dictionary
        will be kept. Otherwise all information stored in target file will be lost. If target file is not valid
        settings file, it will be overwritten. If not in strict mode, :keep_unregistered: has no effect: all settings
        that are not in :allSettings: will be kept.
        All settings in :allSettings: will be stored, even not registered ones.
        Method creates path to target file if one does not exist.
        """

        with self.lock:
            try:
                os.makedirs(os.path.dirname(self.filename), exist_ok=True)
                with open(self.filename, 'w+t') as f:
                    settings = self.allSettings

                    if not self.__strictControl or keep_unregistered:
                        try:
                            saved_settings = json.load(f)
                        except ValueError:
                            saved_settings = None

                        if isinstance(saved_settings, dict):
                            for key, value in saved_settings:
                                if not self.__strictControl:
                                    if key not in self.allSettings:
                                        settings[key] = saved_settings[key]
                                else:
                                    if key not in self.registered:
                                        settings[key] = saved_settings[key]

                    json.dump(settings, f, ensure_ascii=False, indent=4)
            except Exception as err:
                raise SettingsError('failed to save settings: {0}'.format(err))

    def reset(self):
        """Reset all settings to defaults. Unregistered ones are not changed. Note that this method does not
        requires save to be called to apply changes - it applies changes itself by deleting configuration files.
        """

        with self.lock:
            if os.path.exists(self.filename):
                os.remove(self.filename)
            self.allSettings = {}

    def resetSetting(self, setting_name):
        """Reset only single setting to its default value. SettingsError raised if this setting is not registered.
        If not in strict mode, removes key with given name.
        """

        with self.lock:
            if self.__strictControl and setting_name not in self.registered:
                raise SettingsError('writing unregistered setting %s' % setting_name)
            del self.allSettings[setting_name]

    def get(self, setting_name):
        """Return value of setting with given name. In strict mode, trying to get value of unregistered setting that does not exist
        causes SettingsError. You still can get value of unregistered settings that was loaded from file.
        If not in strict mode, returns None for settings that does not exist.
        """

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
        """Return default value for given setting. Raises SettingsError for settings that are not registered.
        Returns None for non-existing settings if not in strict mode.
        """

        with self.lock:
            if setting_name in self.registered:
                return self.registered[setting_name]
            elif self.__strictControl:
                raise SettingsError('reading unregistered setting %s' % setting_name)
            else:
                return None

    def set(self, setting_name, value):
        """Set value for given setting. In strict mode, writing value for setting that does not exist raises
        SettingsError (although you still can modify such values with direct access to allSettings dict).
        """

        with self.lock:
            if self.__strictControl and setting_name not in self.registered:
                raise SettingsError('writing unregistered setting %s' % setting_name)

            if setting_name in self.registered and self.registered[setting_name] == value:
                del self.allSettings[setting_name]
            else:
                self.allSettings[setting_name] = value

    def register(self, setting_name, default_value=None):
        """Register setting with specified name and given default value.
        """

        with self.lock:
            if setting_name not in self.registered:
                self.registered[setting_name] = default_value
            elif self.registered[setting_name] != default_value:
                raise SettingsError('cannot register setting {0}: another one registered with this name'
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
    """Return settings object used to store user-customizable parameters. It is in strict mode.
    """

    global _globalSettings
    if _globalSettings is None:
        _globalSettings = Settings(DEFAULT_SETTINGS_FILE, strict_control=True)
    return _globalSettings


def globalQuickSettings():
    """Return settings object used to store application information that should not be edited by user.
    (just like list of opened file, search history, window sizes and positions, etc)
    """

    global _globalQuickSettings
    if _globalQuickSettings is None:
        _globalQuickSettings = Settings(DEFAULT_QUICK_SETTINGS_FILE)
    return _globalQuickSettings
