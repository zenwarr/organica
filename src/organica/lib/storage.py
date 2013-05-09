import os
import json
import logging

from organica.utils.operations import globalOperationContext
from organica.utils.helpers import tr, readJsonFile, removeLastSlash
from organica.utils.fileop import copyFile, removeFile, isSameFile


logger = logging.getLogger(__name__)


class LocalStorage(object):
    MetadataFilename = 'meta.storage'

    def __init__(self):
        self.__rootDirectory = ''
        self.__metas = dict()

    @staticmethod
    def fromDirectory(root_dir):
        """Create storage initialized from given directory. Read storage meta-information file.
        """

        stor = LocalStorage()
        stor.__rootDirectory = root_dir

        if os.path.exists(root_dir) and os.path.exists(stor.metafilePath):
            with open(stor.metafilePath, 'rt') as f:
                config = None
                try:
                    config = readJsonFile(f)
                except ValueError as err:
                    logger.error('failed to read storage meta-information: {0}'.format(err))

                if config is not None and not isinstance(config, dict):
                    logger.error('failed to read storage meta-information: invalid file format')

                if config:
                    stor.__metas = config

        return stor

    @property
    def metafilePath(self):
        return os.path.join(self.rootDirectory, self.MetadataFilename)

    def saveMetafile(self):
        """Writes meta into metafile. All existing information in metafile will be overwritten.
        """

        with open(self.metafilePath, 'w+t') as f:
            json.dump(self.__metas, f, ensure_ascii=False, indent=4)

    @property
    def rootDirectory(self):
        return self.__rootDirectory

    def addFile(self, source_filename, target_path, remove_source=False):
        """Copy or move source file to storage directory with :target_path:
        :target_path: should be path relative to storage root directory and contain basename. Fails if
        destination exists (use updateFile instead).
        Can add files as well as directories will all its contents.
        Supports operations.
        """

        if not self.rootDirectory:
            raise ValueError('no root directory for storage')

        # get absolute path of destination file
        if not os.path.isabs(target_path):
            target_path = os.path.join(self.rootDirectory, target_path)

        copyFile(source_filename, target_path, remove_source=remove_source)

    def getMeta(self, meta_name, default=None):
        return self.__metas.get(meta_name, default)

    def setMeta(self, meta, value):
        self.__metas[meta] = value
        self.saveMetafile()

    def removeMeta(self, meta_name):
        self.__metas = dict((key, self.__metas[key]) for key in self.__metas.keys() if meta_name != key)
        self.saveMetafile()

    def testMeta(self, meta_name):
        return any((meta_name == key for key in self.__metas.keys()))

    def __eq__(self, other):
        if not isinstance(other, LocalStorage):
            return NotImplemented

        return isSameFile(self.rootDirectory, other.rootDirectory)

    def __ne__(self, other):
        r = self.__eq__(other)
        return not r if r != NotImplemented else r

    @staticmethod
    def isDirectoryStorage(path):
        return os.path.exists(path) and os.path.exists(os.path.join(path, LocalStorage.MetadataFilename))

    def getStoragePath(self, source_path, node):
        from organica.lib.formatstring import FormatString
        import organica.utils.helpers as helpers

        path_template = self.pathTemplate
        if path_template:
            fs = FormatString(path_template)
            fs.registerCustomBlock('@source', (lambda node, token: helpers.removeLastSlash(source_path)))
            formatted = fs.format(node)
            if formatted:
                return formatted
        return os.path.basename(helpers.removeLastSlash(source_path))

    @property
    def pathTemplate(self):
        return self.getMeta('path_template')

    @pathTemplate.setter
    def pathTemplate(self, new_value):
        self.setMeta('path_template', new_value)

    def removeAllFiles(self):
        metafile_path = self.metafilePath
        removeFile(self.rootDirectory, remove_root_dir=False, predicate=(lambda path: not isSameFile(path, metafile_path)))

    def copySettingsFrom(self, other):
        self.__metas = other.__metas
        self.saveMetafile()

    def importFilesFrom(self, other, remove_source):
        metafile_path = other.metafilePath
        copyFile(other.rootDirectory, self.rootDirectory, remove_source=remove_source, remove_root_dir=False,
                 predicate=(lambda path: not isSameFile(path, metafile_path)))
