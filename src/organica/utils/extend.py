import os
import logging
import json

from PyQt4.QtCore import QObject, pyqtSignal, QUuid

from organica.utils.lockable import Lockable
from organica.utils.settings import globalSettings
import organica.utils.constants as constants


logger = logging.getLogger(__name__)


class ObjectPool(QObject, Lockable):
    """Stores objects that can be used as extension points by application. Each object should support
    'group' and 'extensionUuid' attributes.
    ObjectPool wraps each extension object into special class and stores not extension object directly, but wrapper.
    """

    objectAdded = pyqtSignal(object)
    objectRemoved = pyqtSignal(object)

    def __init__(self):
        QObject.__init__(self)
        Lockable.__init__(self)
        self.__objects = []

    def __len__(self):
        with self.lock:
            return len(self.__objects)

    def __iter__(self):
        with self.lock:
            for obj in self.__objects:
                yield obj

    def __contains__(self, obj):
        with self.lock:
            return any((x == obj for x in self.__objects))

    def add(self, obj):
        """Add object (or objects from list/tuple) into pool.
        """

        with self.lock:
            if isinstance(obj, list) or isinstance(obj, tuple):
                for x in obj:
                    x = _PluginObjectWrapper(x)
                    self.__objects.append(x)
                    self.objectAdded.emit(x)
            elif obj is not None:
                obj = _PluginObjectWrapper(obj)
                self.__objects.append(obj)
                self.objectAdded.emit(obj)

    def removeExtensionObjects(self, ext_uuid):
        """Convenience method to remove all objects which are associated with
        given extension UUID
        """

        self.removeObjects(lambda x: hasattr(x, 'extensionUuid') and x.extensionUuid == ext_uuid)

    def removeObjects(self, predicate=None):
        """Remove objects for which predicate is true.
        """

        with self.lock:
            objs_to_remove = [x for x in self.__objects if predicate is None or predicate(x._target)]
            self.__objects = [x for x in self.__objects if not (predicate is None or predicate(x._target))]
            for obj in objs_to_remove:
                self.objectRemoved.emit(obj)

    def removeObject(self, obj):
        self.removeObjects(lambda x: x is obj)

    def objects(self, group=None, predicate=None):
        """Get list of objects with given group and for which predicate is True.
        Group or predicate can be set to None and ignored.
        """

        with self.lock:
            return [x for x in self.__objects if (not group or x.group == group) \
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

    def loadPlugins(self):
        """Load all plugins from plugins directory. Should be called once on program startup. Disabled plugins
        will not be loaded. If plugins directory does not exist, no error will be raised.
        If any plugin fails to load, no error will be raised to let other plugins be loaded.
        """
        logger.debug('loading plugins from {0}'.format(self.pluginsPath))

        if not os.path.exists(self.pluginsPath):
            return

        # iterate over directories in plugins directory
        for name in os.listdir(self.pluginsPath):
            path = os.path.join(self.pluginsPath, name)
            if os.path.isdir(path):
                # check if this is plugin directory
                if os.path.exists(os.path.join(path, self.PLUGIN_CONFIG_FILENAME)):
                    plugin = PluginInfo()
                    plugin.path = path
                    logger.debug('loading plugin {0}...'.format(plugin.name))
                    try:
                        self.__loadPlugin(plugin)
                    except PluginError as err:
                        logger.error('failed to load plugin from {0}: {1}'.format(path, err))
                    else:
                        logger.debug('...loaded successfully')
                    self.__allPlugins.append(plugin)

    def unloadPlugins(self):
        """Unload all loaded plugins. Does not raises an error when any plugin fails to unload to let all plugins
        be unloaded. Objects placed in global object pool by this plugin will be removed from pool first.
        """
        for plugin in self.__allPlugins:
            if plugin.loaded:
                try:
                    self.unloadPlugin(plugin)
                except PluginError as err:
                    logger.error('error while unloading plugin {0}: {1}'.format(plugin.name, err))

    @property
    def pluginsPath(self):
        return os.path.join(constants.data_dir, self.PLUGINS_DIR_NAME)

    @property
    def allPlugins(self):
        """List of PluginInfo objects. Contains not only successfully loaded plugins, but also disabled or
        broken ones.
        """
        return self.__allPlugins

    def enablePlugin(self, plugin, is_enabled=True):
        """Enable or disable plugin. List of disabled plugins is stored in application settings. Plugin will be
        loaded or unloaded to reflect changes.
        """

        plugin = self.__getPlugin(plugin)
        if plugin is None:
            raise PluginError('plugin {0} not found'.format(plugin))

        disabled_plugins_uuids = globalSettings()['disabled_plugins']
        if (plugin.uuid not in disabled_plugins_uuids) != is_enabled:
            if is_enabled:
                # remove uuid from list and reload given plugin
                disabled_plugins_uuids = [uuid for uuid in disabled_plugins_uuids if uuid != plugin.uuid]
                if not plugin.loaded:
                    self.reloadPlugin(plugin)
            else:
                # add to list and unload plugin
                disabled_plugins_uuids.append(plugin.uuid)
                if plugin.loaded:
                    self.unloadPlugin(plugin)
            globalSettings()['disabled_plugins'] = disabled_plugins_uuids

    def reloadPlugin(self, plugin):
        plugin = self.__getPlugin(plugin)
        if plugin is None:
            raise PluginError('plugin {0} not found'.format(plugin))

        if plugin.loaded:
            plugin_module = plugin.module

            self.unloadPlugin(plugin)

            import imp
            imp.reload(plugin_module)
            plugin.module = plugin_module

            self.__loadPlugin(plugin)
        else:
            self.__loadPlugin(plugin)

    def unloadPlugin(self, plugin):
        """Unload plugin. Does not raise any error if plugin is not loaded. Due to Python architecture,
        calling this function does not guarantee that module will be unloaded.
        If extension code fails during unloading, plugin still will be marked as unloaded.
        """
        plugin = self.__getPlugin(plugin)
        if plugin is None:
            raise PluginError('plugin {0} is not found'.format(plugin))

        if plugin.loaded:
            try:
                # call unload routine if exist
                if plugin.plugin_object is not None and hasattr(plugin.plugin_object, 'onUnload'):
                    plugin.plugin_object.onUnload()

                # remove objects associated with plugin
                globalObjectPool().removeExtensionObjects(plugin.uuid)
            except Exception as err:
                raise PluginError('error while unloading plugin {0}: {1}'.format(plugin.name, str(err)))
            else:
                plugin.loaded = False
                plugin.module = plugin.plugin_object = None

    def __loadPlugin(self, plugin):
        config_filename = os.path.join(plugin.path, self.PLUGIN_CONFIG_FILENAME)
        if not os.path.exists(config_filename):
            raise PluginError('{0} file not found'.format(config_filename))

        with open(config_filename, 'rt') as f:
            try:
                info_data = json.load(f)
                plugin.uuid = str(info_data.get('uuid'))
                plugin.name = str(info_data.get('name'))
                plugin.description = str(info_data.get('description'))
                plugin.authors = str(info_data.get('authors'))
            except:
                raise PluginError('invalid {0} file'.format(config_filename))

        # check if uuid is valid
        if not plugin.uuid:
            raise PluginError('uuid is invalid')

        # check if name is valid
        if not plugin.name:
            raise PluginError('name is invalid')

        # import module file
        try:
            import imp

            main_module = os.path.join(plugin.path, self.PLUGIN_MAIN_MODULE)
            if not os.path.exists(main_module):
                raise PluginError('{0} not found'.format(main_module))
            plugin.module = imp.load_source('plugins.{0}'.format(plugin.name), main_module)
        except Exception as err:
            raise PluginError('error during loading module: {0}'.format(err))

        self.__initPlugin(plugin)

        return plugin

    def __getPlugin(self, plugin):
        """Get PluginInfo data from allPlugins list. Argument can be of string (plugin name or uuid), QUuid or
        PluginInfo type. In last case, it uses uuid attribute of PluginInfo to get result.
        """
        if isinstance(plugin, str):
            # it is name or uuid
            r = [x for x in self.__allPlugins if x.name == plugin or x.uuid == plugin]
        elif isinstance(plugin, QUuid):
            r = [x for x in self.__allPlugins if x.uuid == plugin.toString()]
        elif isinstance(plugin, PluginInfo):
            return self.__getPlugin(plugin.uuid)
        return r[0] if r else None

    def __initPlugin(self, plugin):
        try:
            if not hasattr(plugin.module, 'Plugin'):
                raise PluginError('module does not have \'Plugin\' attribute')

            plugin.plugin_object = plugin.module.Plugin()

            if hasattr(plugin.plugin_object, 'onLoad'):
                plugin.plugin_object.onLoad()

            plugin.loaded = True
        except Exception as err:
            plugin.module = plugin.plugin_object = None
            raise PluginError('error during initialization: {0}'.format(err))


_globalPluginManager = None


def globalPluginManager():
    global _globalPluginManager
    if _globalPluginManager is None:
        _globalPluginManager = PluginManager()
    return _globalPluginManager


class Hooks(object):
    allHooks = dict()

    @staticmethod
    def installHook(hook_name, callback):
        if hook_name in Hooks.allHooks:
            Hooks.allHooks[hook_name].append(callback)
        else:
            Hooks.allHooks[hook_name] = [callback]

    @staticmethod
    def uninstallHook(hook_name, callback):
        if hook_name in Hooks.allHooks:
            Hooks.allHooks[hook_name] = [x for x in Hooks.allHooks[hook_name] if x is not callback]

    @staticmethod
    def safeRunHook(hook_name, **kwargs):
        """Call each hook installed. Does not raises any exception from hooks.
        """
        for callback in Hooks.allHooks.get(hook_name, []):
            try:
                callback(**kwargs)
            except Exception as err:
                logger.error('error while processing hook {0}: {1}'.format(err))

    @staticmethod
    def unsafeRunHook(hook_name, **kwargs):
        for callback in Hooks.allHooks.get(hook_name, []):
            callback(**kwargs)

    @staticmethod
    def runHook(hook_name, **kwargs):
        getattr(Hooks, ('un' if constants.debug_plugins else '') + 'runHook')(hook_name, **kwargs)


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
    except Exception as err:
        reportPluginFail(err, plugin_object)
        return default


class _PluginObjectWrapper(object):
    def __init__(self, target):
        self._target = target

    def __getattr__(self, attr_name):
        if attr_name.startswith('_'):
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
