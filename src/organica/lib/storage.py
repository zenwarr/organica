import os, logging, json
from organica.lib.locator import Locator
from PyQt4.QtCore import QObject, pyqtSignal, QSettings

logger = logging.getLogger(__name__)

class StorageError(Exception):
	pass

class PathTemplate:
	def __init__(self, elems = None, fname = ''):
		self.elements = elems if elems else []
		self.filename = fname

class LocalStorage(QObject):
	def __init__(self):
		QObject.__init__()
		self.__lib = None
		self.__rootDir = ''
		self.__config = {}

	@staticmethod
	def loadStorage(lib):
		stor = LocalStorage()
		stor.__lib = lib

		if not lib.testMeta('storage_use'):
			raise StorageError('library does not uses storage')

		root_dir = lib.getMeta('storage_root')
		if root_dir is None:
			raise StorageError('library has no information about storage location')

		# storage path may be absolute or relative to library file directory
		if not os.path.isabs(root_dir):
			root_dir = os.path.join(os.path.dirname(lib.databaseFilename), root_dir)

		if not os.path.isdir(root_dir):
			raise StorageError('storage directory {0} not found'.format(root_dir))

		stor.__rootDir = os.path.normpath(root_dir)

		# read storage config
		config_file = os.path.join(root_dir, 'storage.conf')
		if not os.path.exists(config_file) or not os.access(config_file, os.R_OK):
			raise StorageError('storage config file {0} does not exists or protected'
			                   .format(config_file))

		with open(config_file, 'rt') as cf:
			stor.__config = json.load(cf)

		return stor

	@staticmethod
	def createStorage(lib, root_dir):
		stor = LocalStorage()
		stor.__lib = lib
		stor.__rootDir = os.path.normpath(root_dir)

		if not os.path.exists(root_dir):
			try:
				os.makedirs(root_dir, exists_ok = True)
			except OSerror as err:
				raise StorageError('failed to init storage in {0}: {1}'.format(root_dir, err))

		config_file = os.path.join(root_dir, 'storage.conf')
		if os.path.exists(config_file):
			# importing existing storage configuration
			with open(config_file, 'rt') as cf:
				json.load(cf)
		else:
			with open(config_file, 'wt') as cf:
				json.dump(stor.__config, ensure_ascii = False, indent = 4)

		lib.setMeta('storage_use')
		lib.setMeta('storage_root', root_dir)

		return stor

	def saveConfig(self):
		config_file = os.path.join(self.__rootDir, 'storage.conf')
		try:
			with open(config_file, 'wt') as cf:
				json.dump(config_file, ensure_ascii = False, indent = 4)
		except OSError as err:
			raise StorageError('failed to save configuration in {0}'.format(config_file))

	@property
	def lib(self):
		return self.__lib

	@property
	def rootDirectory(self):
		return self.__rootDir

	@property
	def pathTemplate(self):
		return self.__config['path_template'] if 'path_template' in self.__config else ''

	@pathTemplate.setter
	def pathTemplate(self, value):
		self.__config['path_template'] = value
		self.__saveConfig()

	def isInStorage(self, file_path):
		"""
		Checks if file identified by given absolute file is located under
		storage root directory.
		"""
		if isinstance(file_path, Locator):
			file_path = file_path.absoluteFilePath
		if file_path is None or len(file_path) == 0:
			return False

		if not isabs(file_path): raise ArgumentError('absolute path expected')
		file_path = os.path.normpath(file_path)
		common_pref = os.path.commonprefix(self.__rootDir, file_path) == self.__rootDir
		return os.path.exists(common_pref) and os.path.samefile(self.__rootDir, common_pref)

	def isManaged(self, file_path):
		"""
		Checks if file is managed
		"""
		return self.isInStorage(file_path) and \
				self.lib.object(ObjectFilter.locator(Locator.managedFile(file_path, self)))

	def addFile(self, obj):
		"""
		Add file to storage, flushing object on success
		"""
		if obj is None or not obj.isValid:
			raise ArgumentError('invalid object')

		with OperationContext.newOperation('adding files to storage') as op:
			if obj.locator.isManagedFile and obj.locator.storage == self:
				op.addMessage('file {0} is in storage already'.format(obj.locator))
				return

			source_file = obj.locator.absoluteFilePath
			if not os.path.exists(source_file):
				raise StorageError('source file {0} does not exists'.format(source_file))

			# generate path to which we should copy file
			dest = self.generatePath(obj)
			if dest is None:
				raise StorageError('failed to generate path to {0} file in storage'.format(source_file))

			copy_operation = CopyFilesOperation(source_file, dest)
			op.executeSubOperation(copy_operation)
			if op.state.status != Operation.COMPLETED:
				raise StorageError('failed to copy from {0} to storage ({0})'.format(source_file, dest))

			obj.locator = Locator.managedFile(dest, self)
			obj.flush()

	def generatePath(self, source_object):

