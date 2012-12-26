import os, json, logging
import organica.utils.constants as constants
from organica.utils.singleton import Singleton
from PyQt4.QtCore import QObject, pyqtSignal
from PyQt4.QtGui import QAction, QKeySequence, QMenuBar, QMenu, QToolBar

logger = logging.getLogger(__name__)

class Command(QAction):
    def __init__(self, id, userText, validator = None, default_shortcut = QKeySequence()):
        QAction.__init__(self, userText)
        self.id = id
        self.defaultShortcut = default_shortcut
        self.setShortcut(default_shortcut)
        self.setValidator(validator)

    def resetShortcut(self):
        self.setShortcut(self.defaultShortcut)

    def setValidator(self, validator):
        if validator == self.validator:
            return

        if self.validator is not None:
            self.validator.stateChanged.disconnect(self.setEnabled)
        self.validator = validator
        self.setEnabled(self.validator is not None or self.validator.isActive())
        if self.validator:
            self.validator.connect(self.setEnabled)

class CommandContainer:
    def __init__(self, id, userText = ''):
        self.id = id
        self.userText = userText

    def appendSeparator(self):
        raise NotImplementedError()

    def appendCommand(self, command):
        raise NotImplementedError()

    def appendContainer(self, cont):
        raise NotImplementedError()

class CommandManager(Singleton):
    SHORTCUTS_CONFIG_FILENAME = 'shortcuts.conf'

    def singleton_init(self):
        pass

    def __singleton_init(self):
        self.commands = {}
        self.containers = {}
        self.shortcutMapping = {}
        self.validators = {}

    def addCommand(self, cmd):
        if cmd is not None and len(cmd.id) > 0 and not self.commands.contains(cmd.id):
            if cmd.id in self.shortcutMapping:
                cmd.setShortcut(self.shortcutMapping[cmd.id])
            self.commands[cmd.id] = cmd
        else:
            raise ArgumentError('invalid command')

    def addCommand(self, slot, cmd_id, user_text, validator = None, def_shortcut = QKeySequence()):
        if len(cmd_id) == 0 or cmd_id in self.commands:
            raise ArgumentError('invalid command id')
        cmd = Command(cmd_id, user_text, validator, def_shortcut)
        if slot is not None:
            cmd.triggered.connect(slot)
        self.addCommand(cmd)
        return cmd

    def command(self, id):
        return self.commands[id] if id in self.commands else None

    def command(self, shortcut):
        for c in self.commands.values():
            if c.shortcut == shortcut:
                return c
        return None

    def addContainer(self, container):
        if not container or container.id in self.containers:
            raise ArgumentError('invalid container')
        self.containers[container.id] = container

    def container(self, id):
        return self.containers[id] if id in self.containers else None

    def addValidator(self, validator):
        if validator is None or validator.id in self.validators:
            raise ArgumentError('invalid validator')
        self.validators[validator.id] = validator

    def validator(self, id):
        return self.validators[id] if id in self.validators else None

    def saveShortcuts(self):
        """
        Saves all shortcuts that are different from default shortcuts into file.
        Calling this function will reset all shortcuts for extensions that are
        not loaded at this moment.
        """
        conf_file = os.path.join(constants.data_dir, self.SHORTCUTS_CONFIG_FILENAME)
        try:
            f = open(conf_file, 'wt')
            with f:
                json.dump(self.shortcutMapping, f, ensure_ascii=False, indent=4)
        except OSError as err:
            logger.error('failed to save shortcuts config: {0}'.format(str(err)))

    def loadShortcuts(self):
        conf_file = os.path.join(constants.data_dir, self.SHORTCUTS_CONFIG_FILENAME)
        if not os.path.exists(conf_file):
            return
        try:
            f = open(conf_file, 'rt')
            with f:
                s = json.load(f)
                if not isinstance(s, dict):
                    raise OSError('invalid config file format')
                self.shortcutMapping = s
        except OSError as err:
            logger.error('failed to read shortcuts config: {0}'.format(str(err)))


class QMenuCommandContainer(QMenu, CommandContainer):
    def __init__(self, id, user_text, parent = None):
        QMenu.__init__(self, parent)
        CommandContainer.__init__(self, id, user_text)

    def appendCommand(self, command):
        if isinstance(str, command):
            command = CommandManager().command(command)
        if command is not None:
            self.addAction(command)

    def appendContainer(self, container):
        if isinstance(str, container):
            container = CommandManager().container(container)
        if container is not None:
            if not isinstance(QMenuCommandContainer, container):
                raise TypeError('menu container expected')
            self.addMenu(container)

    def appendSeparator(self):
        self.addSeparator()

class QMenuBarCommandContainer(QMenuBar, CommandContainer):
    def __init__(self, id, parent = None):
        QMenuBar.__init__(self, parent)
        CommandContainer.__init__(self, id)

    def appendCommand(self, command):
        if isinstance(str, command):
            command = CommandManager().command(command)
        if command is not None:
            self.addAction(command)

    def appendContainer(self, container):
        if isinstance(str, container):
            command = CommandManager().container(command)
        if container is not None:
            if not isinstance(QMenuCommandContainer, container):
                raise TypeError('menu container expected')
            self.addMenu(container)

    def appendSeparator(self):
        self.addSeparator()

class QToolBarCommandContainer(QToolBar, CommandContainer):
    def __init__(self, id, userText, parent = None):
        QToolBar.__init__(self, parent)
        CommandContainer.__init__(self, id, userText)

    def addCommand(self, command):
        if isinstance(str, command):
            command = CommandManager().command(command)
        if command is not None:
            self.addAction(command)

    def addContainer(self, container):
        raise NotImplementedError('containers cannot be added into toolbar')

    def addSeparator(self):
        self.addSeparator()

class StateValidator(QObject):
    stateChanged = pyqtSignal(bool)

    def __init__(self, id):
        QObject.__init__(self)
        self.__id = id

    def isActive(self):
        raise NotImplementedError()

    @property
    def id(self):
        return self.__id

class StandardStateValidator(StateValidator):
    def __init__(self, id):
        StateValidator.__init__(self, id)
        self.__isActive = False

    def isActive(self):
        return self.__isActive

    def activate(self):
        if not self.__isActive:
            self.__isActive = True
            self.stateChanged.emit(True)

    def deactivate(self):
        if self.__isActive:
            self.__isActive = False
            self.stateChanged.emit(False)

    def setActive(self, value):
        if self.__isActive != value:
            self.__isActive = value
            self.stateChanged.emit(value)