import os
import json

from PyQt4.QtCore import QObject, pyqtSignal
from PyQt4.QtGui import QAction, QKeySequence, QMenuBar, QMenu, QToolBar

import organica.utils.constants as constants


class Command(QAction):
    def __init__(self, id, user_text, validator=None, default_shortcut=QKeySequence()):
        QAction.__init__(self, user_text, None)
        self.id = id
        self.defaultShortcut = QKeySequence(default_shortcut)
        self.setShortcut(default_shortcut)
        self.__validator = None
        self.validator = validator

    def resetShortcut(self):
        """Reset command shortcut to default value
        """
        self.setShortcut(self.defaultShortcut)

    @property
    def validator(self):
        """Validator is object that determines if command should be enabled at current moment.
        None validator means that command is always enabled.
        """
        return self.__validator

    @validator.setter
    def validator(self, new_validator):
        if isinstance(new_validator, str):
            new_validator = globalCommandManager().validator(new_validator)

        if new_validator is self.__validator:
            return

        if self.__validator is not None:
            self.__validator.stateChanged.disconnect(self.setEnabled)

        self.__validator = new_validator
        self.setEnabled(not self.__validator or self.__validator.isActive)
        if self.__validator is not None:
            self.__validator.activeChanged.connect(self.setEnabled)


class ShortcutScheme(object):
    def __init__(self, shortcuts_map=None):
        self.shortcuts = shortcuts_map or dict()

    def save(self, filename, keep_unloaded=True):
        """Save scheme into file with :filename:. If :filename: is relative path,
        it will be resolved with constants.data_dir base.
        If :keep_unloaded: is true, scheme will be merged with one already saved in target
        file (shortcuts for commands not registered at this moment will not be overwritten).
        Otherwise scheme saved in file will have only currently registered shortcuts.
        """

        filename = self.__getFilename(filename)

        if not os.path.exists(filename):
            return

        with open(filename, 'w+t') as f:
            scheme = self.shortcuts

            if keep_unloaded:
                saved_scheme = json.load(f)
                if saved_scheme and isinstance(saved_scheme, dict):
                    for cmd_id in saved_scheme.keys():
                        if cmd_id not in scheme:
                            saved_scheme[cmd_id] = saved_scheme[cmd_id]

            json.dump(scheme, f, ensure_ascii=False, indent=4)

    @staticmethod
    def load(filename):
        """Load scheme from file :filename:
        """

        filename = ShortcutScheme.__getFilename(filename)

        if not os.path.exists(filename):
            return

        with open(filename, 'rt') as f:
            loaded_struct = json.load(f)
            if not isinstance(loaded_struct, dict):
                raise TypeError('invalid shortcut scheme file {0}'.format(filename))
            shortcutMapping = dict((cmd_id, QKeySequence(shortcut)) \
                                        for cmd_id, shortcut in loaded_struct.items())
        return ShortcutScheme(shortcutMapping)

    @staticmethod
    def __getFilename(filename):
        return filename if os.path.isabs(filename) else os.path.join(constants.data_dir,
                                                                     filename)


class CommandManager(object):
    """Command manager manages commands and holds shortcut scheme.
    """

    SHORTCUTS_CONFIG_FILENAME = 'shortcuts.conf'

    def __init__(self):
        self.commands = {}
        self.containers = {}
        self.validators = {}
        self.__shortcutScheme = ShortcutScheme()

    @property
    def shortcutScheme(self):
        return self.__shortcutScheme

    @shortcutScheme.setter
    def shortcutScheme(self, new_scheme):
        if self.__shortcutScheme is new_scheme:
            return

        # update shortcuts for all loaded commands
        for cmd in self.commands.values():
            if cmd.shortcut() != cmd.defaultShortcut:
                if cmd.id in self.__shortcutScheme:
                    cmd.setShortcut(self.__shortcutScheme.shortcuts[cmd.id])
                else:
                    cmd.resetShortcut()

    def addCommand(self, cmd):
        """Add given command to CommandManager. This allows user to manage command,
        change it shortcut, etc.
        """

        if not cmd or not cmd.id or cmd.id in self.commands:
            raise TypeError('invalid argument: cmd')

        # if current shortcut scheme redefines key for this command
        if cmd.id in self.shortcutScheme.shortcuts:
            cmd.setShortcut(self.shortcutScheme.shortcuts[cmd.id])
        self.commands[cmd.id] = cmd

    def addNewCommand(self, slot, cmd_id, user_text, validator=None, default_shortcut=QKeySequence()):
        """Create new command and add it with CommandManager.addCommand
        """

        if not cmd_id or cmd_id in self.commands:
            raise TypeError('invalid argument: cmd_id')
        cmd = Command(cmd_id, user_text, validator, default_shortcut)
        if slot:
            cmd.triggered.connect(slot)
        self.addCommand(cmd)
        return cmd

    def command(self, id):
        """Get command by its id or shortcut
        """

        if isinstance(id, str):
            return self.commands.get(id)
        else:
            for c in self.commands.values():
                if c.shortcut == id:
                    return c
            return None

    def addContainer(self, container):
        if not container or container.id in self.containers:
            raise TypeError('invalid argument: container')
        self.containers[container.id] = container

    def container(self, id):
        return self.containers.get(id)

    def addValidator(self, validator):
        if not validator or validator.id in self.validators:
            raise TypeError('invalid argument: validator')
        self.validators[validator.id] = validator

    def validator(self, id):
        return self.validators.get(id)

    def saveShortcutScheme(self):
        self.shortcutScheme.save(self.shortcutsConfigFilename())

    def loadShortcutScheme(self):
        self.shortcutScheme = ShortcutScheme.load(self.shortcutsConfigFilename())

    def shortcutsConfigFilename(self):
        return os.path.join(constants.data_dir, self.SHORTCUTS_CONFIG_FILENAME)


_globalCommandManager = None


def globalCommandManager():
    global _globalCommandManager
    if not _globalCommandManager:
        _globalCommandManager = CommandManager()
    return _globalCommandManager


class QMenuCommandContainer(QMenu):
    def __init__(self, id, user_text, parent=None):
        QMenu.__init__(self, user_text, parent)
        self.id = id
        self.userText = user_text

    def appendCommand(self, command):
        if isinstance(command, str):
            command = globalCommandManager().command(command)
        if not command:
            raise TypeError('invalid argument: command')
        self.addAction(command)

    def appendContainer(self, container):
        if isinstance(container, str):
            container = globalCommandManager().container(container)
        if not container:
            raise TypeError('invalid argument: command')
        if not isinstance(container, QMenuCommandContainer):
            raise TypeError('menu container expected')
        self.addMenu(container)

    def appendSeparator(self):
        self.addSeparator()


class QMenuBarCommandContainer(QMenuBar):
    def __init__(self, id, parent=None):
        QMenuBar.__init__(self, parent)
        self.id = id
        self.userText = ''

    def appendCommand(self, command):
        if isinstance(command, str):
            command = globalCommandManager().command(command)
        if not command:
            raise TypeError('invalid argument: command')
        self.addAction(command)

    def appendContainer(self, container):
        if isinstance(container, str):
            container = globalCommandManager.container(container)
        if not container:
            raise TypeError('invalid argument: command')
        if not isinstance(container, QMenuCommandContainer):
            raise TypeError('menu container expected')
        self.addMenu(container)

    def appendSeparator(self):
        self.addSeparator()


class QToolBarCommandContainer(QToolBar):
    def __init__(self, id, user_text, parent=None):
        QToolBar.__init__(self, parent)
        self.id = id
        self.userText = user_text

    def appendCommand(self, command):
        if isinstance(command, str):
            command = globalCommandManager().command(command)
        if not command:
            raise TypeError('invalid argument: command')
        self.addAction(command)

    def appendContainer(self, container):
        raise NotImplementedError('containers cannot be added to toolbar')

    def appendSeparator(self):
        self.addSeparator()


class StateValidator(QObject):
    activeChanged = pyqtSignal(bool)

    def __init__(self, id):
        QObject.__init__(self)
        self.__id = id

    @property
    def isActive(self):
        raise NotImplementedError()

    @property
    def id(self):
        return self.__id


class StandardStateValidator(StateValidator):
    def __init__(self, id):
        StateValidator.__init__(self, id)
        self.__isActive = False

    @property
    def isActive(self):
        return self.__isActive

    @isActive.setter
    def isActive(self, value):
        if self.__isActive != value:
            self.__isActive = value
            self.activeChanged.emit(value)

    def activate(self):
        self.isActive = True

    def deactivate(self):
        self.isActive = False
