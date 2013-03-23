# The MIT License
#
# Copyright (c) 2013 zenwarr
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

"""This module provides functionality to read and store application settings. All settings are stored
in JSON format, and syntax parsing implemented with standard JSON module, having all its advantages and
lacks. For example, it cannot store binary data.
Before using module functions you should configure it. Configuring is done by initializing four variables:
    defaultSettingsFilename is filename (without path) for Settings object returned by globalSettings
    function.
    defaultQuickSettingsFilename is filename (without path) for Settings object returned by globalQuickSettings
    function.
    defaultSettingsDirectory is directory path where settings files are be stored if you do not specify
    absolute path for paths.
    warningOutputRoutine is method module code will call when some non-critical errors are found.
Or you can use defaultConfigure function passing application name to it.

Example:

    import settings
    import logging

    # ...
    logger = logging.getLogger(__name__)
    # ...

    # application initialization
    settings.defaultConfigure('MyApplication')
    settings.warningOutputRoutine = logger.warn

    # ...

    # register application settings
    s = settings.globalSettings()
    s.register('god_mode', False)

    # ...

    # read
    is_in_god_mode = s['god_mode']

    # save
    s['god_mode'] = is_in_god_mode

    # reset one setting to default value
    del s['god_mode']

    # reset all settings
    s.reset()

Each Settings object can be in strict mode or not. When object is in strict mode, it allows writing only
registered settings. Default values can be used only with strict Settings object.
"""

__author__ = 'zenwarr'


import os
import sys
import json
import threading


class SettingsError(Exception):
    pass


def defaultConfigure(app_name):
    global defaultSettingsFilename, defaultQuickSettingsFilename, defaultSettingsDirectory

    defaultSettingsFilename = app_name + '.conf'
    defaultQuickSettingsFilename = app_name + '.qconf'

    if sys.platform.startswith('win'):
        defaultSettingsDirectory = os.path.expanduser('~/Application Data/' + app_name)
    elif sys.platform.startswith('darwin'):
        defaultSettingsDirectory = os.path.expanduser('~/Library/Application Support/' + app_name)
    else:
        defaultSettingsDirectory = os.path.expanduser('~/.' + app_name)


defaultSettingsFilename = ''
defaultQuickSettingsFilename = ''
defaultSettingsDirectory = ''
warningOutputRoutine = None


class Settings(object):
    def __init__(self, filename, strict_control=False):
        self.lock = threading.RLock()
        self.__filename = filename
        self.allSettings = {}
        self.registered = {}
        self.__strictControl = strict_control

    @property
    def filename(self):
        return self.__filename if os.path.isabs(self.__filename) else os.path.join(defaultSettingsDirectory, self.__filename)

    def load(self):
        """Reloads settings from configuration file. If settings filename does not exist or empty, no error raised
        (assuming that all settings has default values). But if file exists but not accessible, SettingsError
        will be raised. Invalid file structure also causes SettingsError to be raised.
        Stored keys that are not registered will cause warning message, but it is not critical error (due
        to compatibility with future versions and plugins). Unregistered settings are placed in allSettings dictionary
        as well as registered ones.
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
                            if warningOutputRoutine is not None:
                                warningOutputRoutine('unregistered setting in config file {0}: {1}'.format(self.filename, key))
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
        # under tests we should always return default values for all settings without reading
        # configuration file. This is possible only if strict_control is disabled.
        from organica.utils.constants import test_run
        _globalSettings = Settings(defaultSettingsFilename, strict_control=not test_run)
    return _globalSettings


def globalQuickSettings():
    """Return settings object used to store application information that should not be edited by user.
    (just like list of opened file, search history, window sizes and positions, etc)
    """

    global _globalQuickSettings
    if _globalQuickSettings is None:
        _globalQuickSettings = Settings(defaultQuickSettingsFilename)
    return _globalQuickSettings
