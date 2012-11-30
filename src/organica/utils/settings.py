import os, logging, json
import organica.utils.constants as constants
from organica.utils.singleton import Singleton
from PyQt4 import QtCore

logger = logging.getLogger(__name__)

class SettingError(Exception):
	def __init__(self, desc):
		super().__init__(desc)

class Settings(Singleton):
	"""
	This class is used to access application settings. Settings are stored in
	human-readable (and human-editable) form (using JSON). Please use this class only
	with settings that are sensible to user. At example, window positions, list of last opened
	file, etc. should be processed with QuickSettings class.
	"""

	configFilename = 'organica.conf'
	allSettings = {}
	registered = {}

	@property
	def configFilepath(self):
		return os.path.join(constants.data_dir, self.configFilename)

	def load(self):
		"""
		Reloads settings from configuration file
		"""

		self.allSettings = {}

		if not os.path.exists(self.configFilepath):
			# this is not an error
			return

		try:
			sf = open(self.configFilepath, 'rt')
		except OSError as err:
			logger.warn('cannot load config file %s: %s', self.configFilepath, str(err))
		else:
			with sf:
				settings = json.load(sf)
				for k, v in settings.items():
					if k in self.registered:
						self.allSettings[k] = v
					else:
						logger.warn('unregistered setting in config file: %s', k)

	def save(self):
		"""
		Store all settings into configuration file
		"""

		try:
			os.makedirs(os.path.dirname(self.configFilepath), exist_ok=True)
			sf = open(self.configFilepath, 'wt')
		except OSError as err:
			logger.warn('cannot write to config file %s: %s', self.configFilepath, str(err))
		else:
			with sf:
				json.dump(self.allSettings, sf, ensure_ascii=False, indent=4)

	def reset(self, resetCommon = False):
		"""
		Reset all settings to defaults.
		"""

		try:
			os.remove(self.configFilepath)
			self.allSettings = {}
		except OSError as err:
			logger.error('failed to clear config file %s: %s', self.configFilepath, str(err))

	def resetSetting(self, settingName):
		if settingName not in self.registered:
			raise SettingError('writing unregistered setting %s' % settingName)
		del self.allSettings[settingName]

	def get(self, settingName):
		if settingName in self.allSettings:
			return self.userSettings[settingName]
		elif settingName in self.registered:
			return self.registered[settingName]['default']
		else:
			raise SettingError('reading unregistered setting %s' % settingName)

	def defaultValue(self, settingName):
		if settingName in self.registered:
			return self.registered[settingName]['default']
		else:
			raise SettingError('reading unregistered setting %s' % settingName)

	def set(self, settingName, value):
		if settingName not in self.registered:
			raise SettingError('writing unregistered setting %s' % settingName)
		if self.registered[settingName]['default'] == value:
			del self.allSettings[settingName]
		else:
			self.allSettings[settingName] = value

	def register(self, settingName, defaultValue = None):
		"""
		Registers setting with specified name and default value.
		"""
		if settingName not in self.registered:
			self.registered[settingName] = {'default': defaultValue}
		else:
			raise SettingError('cannot register setting {0}: another one registed with this name' \
			                   .format(settingName))

class QuickSettings(QtCore.QSettings):
	configFilename = 'organica.store';
	allSettings = {}

	def __init__(self):
		super().__init__(os.path.join(constants.data_dir,
		                              self.configFilename),
						 QtCore.QSettings.IniFormat);

	@property
	def configFilepath(self):
		return os.path.join(constants.app_dir, self.configFilename)

