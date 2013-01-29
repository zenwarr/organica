import os
import logging
import json

from PyQt4.QtCore import QObject, pyqtSignal, QUuid

from organica.utils.lockable import Lockable
from organica.utils.settings import globalSettings
import organica.utils.constants as constants


logger = logging.getLogger(__name__)


class ObjectPool(QObject, Lockable):
    """ObjectPool stores objects that can be used as extension points for
    application. Each object stored should have 'group' and 'extensionUuid'
    attributes.
    """

    objectAdded = pyqtSignal(object)
    objectRemoved = pyqtSignal(object)

    def __init__(self):
        QObject.__init__(self)
        Lockable.__init__(self)
        self._objects = []

    def __len__(self):
        with self.lock:
            return len(self._objects)

    def __iter__(self):
        with self.lock:
            for obj in self._objects:
                yield obj

    def __contains__(self, obj):
        with self.lock:
            return any((x == obj for x in self._objects))

    def add(self, obj):
        """Add object into pool. You should not add objects directly into _objects list.
        """

        with self.lock:
            if obj is not None:
                if isinstance(obj, list) or isinstance(obj, tuple):
                    for x in obj:
                        x = _PluginObjectWrapper(x)
                        self._objects.append(x)
                        self.objectAdded.emit(x)
                else:
                    obj = _PluginObjectWrapper(obj)
                    self._objects.append(obj)
                    self.objectAdded.emit(obj)

    def removeExtensionObjects(self, ext_uuid):
        """Convenience method to remove all objects which are assotiated with
        given extension UUID
        """

        self.removeObjects(lambda x: hasattr(x, 'extensionUuid') and x.extensionUuid == ext_uuid)

    def removeObjects(self, predicate=None):
        """Remove objects for which predicate is true.
        """

        with self.lock:
            objs_to_remove = [x for x in self._objects if predicate is None or predicate(x._target)]
            self._objects = [x for x in self._objects if predicate is not None and not predicate(x._target)]
            for obj in objs_to_remove:
                self.objectRemoved.emit(obj)

    def removeObject(self, obj):
        self.removeObjects(lambda x: x is obj)

    def objects(self, group=None, predicate=None):
        """Get list of objects with given group and for which predicate is True.
        Group or predicate can be set to None and ignored.
        """

        with self.lock:
            return [x for x in self._objects if (not group or x.group == group) \
                    and (predicate is None or predicate(x))]

    def __getitem__(self, group_name):
        return self.objects(group_name)


_globalObjectPool = None


def globalObjectPool():
    global _globalObjectPool
    if _globalObjectPool is None:
        _globalObjectPool = ObjectPool()
    return _globalObjectPool


class PluginInfo(object):
    def __init__(self):
        self.path = ''
        self.uuid = None
        self.name = ''
        self.description = ''
        self.authors = []
        self.module = None
        self.plugin_object = None
        self.loaded = False
        self.enabled = True

    def __str__(self):
        return self.uuid


class PluginError(Exception):
    pass


class PluginManager(object):
    PLUGINS_DIR_NAME = 'plugins'
    PLUGIN_CONFIG_FILENAME = 'plugin.info'
    PLUGIN_MAIN_MODULE = 'plugin.py'

    def __init__(self):
        self.__allPlugins = []
        self.__globalSettings = []
        globalSettings().register('disabled_plugins', [])

    def loadPlugins(self):
        """Load all plugins from plugins directory. Should be called once on program
        startup. Disabled plugins will not be loaded. Does not raises an error when any
        plugin fails to let other plugins to be loaded.
        """
        if not os.path.exists(self.pluginsPath):
            return

        for name in os.listdir(self.pluginsPath):
            path = os.path.join(self.pluginsPath, name)
            if os.path.isdir(path):
                # check if this is plugin directory
                if os.path.exists(os.path.join(path, self.PLUGIN_CONFIG_FILENAME)):
                    plugin = PluginInfo()
                    plugin.path = path
                    try:
                        self.__loadPlugin(plugin)
                    except PluginError as err:
                        logger.error('failed to load plugin from {0}: {1}'.format(path, err))
                    self.__allPlugins.append(plugin)

    def unloadPlugins(self):
        """Unload all loaded plugins. Does not raises an error when any plugin fails to
        let all plugins to be unloaded.
        """
        for plugin in self.__allPlugins:
            try:
                globalObjectPool().removeExtensionObjects(plugin.uuid)
                self.unloadPlugin(plugin)
            except PluginError as err:
                logger.error('error while unloading plugin {0}: {1}'.format(plugin.name, err))

    @property
    def pluginsPath(self):
        return os.path.join(constants.data_dir, self.PLUGINS_DIR_NAME)

    @property
    def allPlugins(self):
        """List of PluginInfo objects.
        """
        return self.__allPlugins

    @property
    def disabledPluginsUuids(self):
        """List of UUIDs for plugins that are disabled.
        """
        return globalSettings()['disabled_plugins']

    def enablePlugin(self, plugin, is_enabled=True):
        plugin = self.__getPlugin(plugin)
        if plugin is None:
            raise PluginError('plugin {0} not found'.format(plugin))
        is_already_enabled = plugin.uuid in self.__disabledPlugins
        if is_already_enabled != is_enabled:
            if is_enabled:
                self.__disabledPlugins = [x for x in self.__disabledPlugins if x.uuid != plugin.uuid]
                if not plugin.loaded:
                    self.reloadPlugin(plugin)
            else:
                self.__disabledPlugins.append(plugin.uuid)
                if plugin.loaded:
                    self.unloadPlugin(plugin)
            globalSettings()['disabled_plugins'] = self.__disabledPlugins

    def reloadPlugin(self, plugin):
        plugin = self.__getPlugin(plugin)
        if plugin is None:
            raise PluginError('plugin {0} not found'.format(plugin))

        if plugin.loaded:
            self.unloadPlugin(plugin)

        self.__loadPlugin(plugin)

    def unloadPlugin(self, plugin):
        plugin = self.__getPlugin(plugin)
        if plugin is None:
            raise PluginError('plugin {0} is not found'.format(plugin))

        if plugin.loaded:
            try:
                if plugin.plugin_object and hasattr(plugin.plugin_object, 'onUnload'):
                    plugin.plugin_object.onUnload()
                plugin.loaded = False
                plugin.module = plugin.plugin_object = None
            except Exception as err:
                raise PluginError('failed to unload plugin {0}: error while unintializing: {1}' \
                                  .format(plugin.name, str(err)))

    def __loadPlugin(self, plugin):
        config_filename = os.path.join(plugin.path, self.PLUGIN_CONFIG_FILENAME)
        if not os.path.exists(config_filename):
            raise PluginError('failed to load plugin {1}: {0} file not found in plugin directory' \
                              .format(self.PLUGIN_CONFIG_FILENAME, plugin.path))

        with open(config_filename, 'rt') as f:
            try:
                info_data = json.load(f)
                plugin.uuid = str(info_data['uuid'])
                plugin.name = str(info_data['name'])
                plugin.description = str(info_data['description'])
                plugin.authors = str(info_data['authors'])
            except:
                raise PluginError('failed to load plugin {1}: invalid {0} file' \
                                  .format(self.PLUGIN_CONFIG_FILENAME, plugin.path))

        # check if uuid is valid
        if not plugin.uuid:
            raise PluginError('failed to load plugin {0}: uuid is invalid' \
                              .format(plugin.path))

        # check if name is valid
        if not plugin.name:
            raise PluginError('failed to load plugin {0}: name is invalid' \
                              .format(plugin.path))

        # import module file
        try:
            import imp

            main_module = os.path.join(plugin.path, self.PLUGIN_MAIN_MODULE)
            if not os.path.exists(main_module):
                raise PluginError('failed to load plugin {0}: {1} not found' \
                                  .format(plugin.name, self.PLUGIN_MAIN_MODULE))
            plugin.module = imp.load_source('plugins.{0}'.format(plugin.name), main_module)
        except Exception as err:
            raise PluginError('failed to load plugin {0}: error during loading module: {1}' \
                              .format(plugin.name, str(err)))

        try:
            if not hasattr(plugin.module, 'Plugin'):
                raise PluginError('failed to load plugin {0}: module does not have \'Plugin\' attribute' \
                                  .format(plugin.name))

            plugin.plugin_object = plugin.module.Plugin()

            if hasattr(plugin.plugin_object, 'onLoad'):
                plugin.plugin_object.onLoad()

            plugin.loaded = True
        except Exception as err:
            plugin.module = plugin.plugin_object = None
            raise PluginError('failed to load plugin {0}: error during initialization: {1}' \
                              .format(plugin.name, str(err)))

        return plugin

    def __getPlugin(self, plugin):
        if isinstance(plugin, str):
            # it is name or uuid
            r = [x for x in self.__allPlugins if x.name == plugin or x.uuid == plugin]
        elif isinstance(plugin, QUuid):
            r = [x for x in self.__allPlugins if x.uuid == plugin.toString()]
        elif isinstance(plugin, PluginInfo):
            return self.__getPlugin(plugin.uuid)
        return r[0] if r else None


_globalPluginManager = None


def globalPluginManager():
    global _globalPluginManager
    if _globalPluginManager is None:
        _globalPluginManager = PluginManager()
    return _globalPluginManager


def Hooks(object):
    _allHooks = dict()

    @staticmethod
    def installHook(hook_name, callback):
        if hook_name in Hooks._allHooks:
            Hooks._allHooks[hook_name].append(callback)
        else:
            Hooks._allHooks[hook_name] = [callback]

    @staticmethod
    def uninstallHook(hook_name, callback):
        if hook_name in Hooks._allHooks:
            Hooks._allHooks[hook_name] = [x for x in Hooks._allHooks[hook_name] if x is not callback]

    @staticmethod
    def safeRunHook(hook_name, **kwargs):
        """Call each hook installed. Does not raises any exception from hooks.
        """
        for callback in Hooks._allHooks.get(hook_name, []):
            try:
                callback(**kwargs)
            except Exception as err:
                logger.error('error while processing hook {0}: {1}'.format(err))

    @staticmethod
    def unsafeRunHook(hook_name, **kwargs):
        for callback in Hooks._allHooks.get(hook_name, []):
            callback(**kwargs)

    def runHook(self, hook_name, **kwargs):
        getattr(self, ('un' if constants.debug_plugins else '') + 'runHook')(hook_name, **kwargs)


def reportPluginFail(error, plugin_object):
    plugin_title = ''
    try:
        if hasattr(plugin_object, 'name'):
            plugin_title = plugin_object.name
        elif hasattr(plugin_object, 'uuid'):
            plugin_title = plugin_object.uuid
    except:
        pass

    logger.error('plugin {0} error: {1}'.format(plugin_title, error))


def pluginGetattr(plugin_object, attr_name, default=None):
    try:
        if hasattr(plugin_object, attr_name):
            return getattr(plugin_object, attr_name)
    except:
        return default


class _PluginObjectWrapper(object):
    def __init__(self, target):
        self._target = target

    def __getattr__(self, attr_name):
        if attr_name.startswith('_') or attr_name.startswith('_PluginObjectWrapper'):
            return object.__getattr__(self, attr_name)
        if self._target is not None:
            if not constants.debug_plugins:
                try:
                    return getattr(self._target, attr_name)
                except Exception as err:
                    reportPluginFail(err, self._target)
                except:
                    reportPluginFail(None, self._target)
            else:
                return getattr(self._target, attr_name)
        return None

    def __setattr__(self, attr_name, attr_value):
        if attr_name.startswith('_') or attr_name.startswith('_PluginObjectWrapper'):
            object.__setattr__(self, attr_name, attr_value)
        if self._target is not None:
            if not constants.debug_plugins:
                try:
                    setattr(self._target, attr_name, attr_value)
                except Exception as err:
                    reportPluginFail(err, self._target)
                except:
                    reportPluginFail(None, self._target)
            else:
                setattr(self._target, attr_name, attr_value)

    def __getitem__(self, item):
        if self._target is not None:
            if not constants.debug_plugins:
                try:
                    return self._target[item]
                except Exception as err:
                    reportPluginFail(err, self._target)
                except:
                    reportPluginFail(None, self._target)
            else:
                return self._target[item]
        return None

    def __setitem__(self, item, value):
        if self._target is not None:
            if not constants.debug_plugins:
                try:
                    self._target[item] = value
                except Exception as err:
                    reportPluginFail(err, self._target)
                except:
                    reportPluginFail(None, self._target)
            else:
                self._target[item] = value
        return None

    def __delitem__(self, item):
        if self._target is not None:
            if not constants.debug_plugins:
                try:
                    del self._target[item]
                except Exception as err:
                    reportPluginFail(err, self._target)
                except:
                    reportPluginFail(None, self._target)
            else:
                del self._target[item]
        return None

    def __iter__(self):
        if self._target is not None:
            if not constants.debug_plugins:
                try:
                    return iter(self._target)
                except Exception as err:
                    reportPluginFail(err, self._target)
                except:
                    reportPluginFail(None, self._target)
            else:
                return iter(self._target)
        return None

    def __eq__(self, other):
        if self._target is not None:
            if isinstance(other, _PluginObjectWrapper):
                return self._target == other._target
            else:
                return self._target == other
        return False

    def __ne__(self, other):
        return not self.__eq__(other)
