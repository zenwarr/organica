import os
import json
import logging

from organica.utils.operations import globalOperationContext
from organica.utils.helpers import tr, readJsonFile, removeLastSlash


logger = logging.getLogger(__name__)


class LocalStorage(object):
    STORAGE_METADATA_FILENAME = 'storage.meta'

    def __init__(self):
        self.__rootDirectory = ''
        self.__metas = {}
        self.__config = dict()

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
                    stor.__config = config

        return stor

    @property
    def metafilePath(self):
        return os.path.join(self.rootDirectory, self.STORAGE_METADATA_FILENAME)

    def saveMetafile(self):
        """Writes meta into metafile. All existing information in metafile will be overwritten.
        """

        with open(self.metafilePath, 'w+t') as f:
            json.dump(self.__config, f, ensure_ascii=False, indent=4)

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

        target_path = removeLastSlash(target_path)
        source_filename = removeLastSlash(source_filename)

        if os.path.isabs(target_path):
            raise ValueError('invalid argument: target_path should be relative')

        if not os.path.exists(source_filename):
            raise OSError('source file {0} not found'.format(source_filename))

        # get absolute path of destination file
        absolute_dest_path = os.path.join(self.rootDirectory, target_path)

        # ensure that destination does not exists
        if os.path.exists(absolute_dest_path):
            raise OSError('destination {0} already exists'.format(absolute_dest_path))

        # ensure destination parent directories are created. If not, create ones
        if not os.path.exists(os.path.dirname(absolute_dest_path)):
            os.makedirs(os.path.dirname(absolute_dest_path), exist_ok=True)

        # if source is a link, do not resolve it, but just create new one in target directory and return
        if os.path.islink(source_filename):
            link_target = os.readlink(source_filename)
            # resolve relative links depending on link directory
            if not os.path.isabs(link_target):
                link_target = os.path.join(os.path.dirname(source_filename), link_target)
            os.symlink(link_target, absolute_dest_path)
            return

        # create new operation and execute work in its context
        source_basename = os.path.basename(source_filename)
        with globalOperationContext().newOperation('copying {0}'.format(source_basename)) as operation:
            def do_add(src_path, dest_path, remove_source, progress_increment):
                import shutil

                if os.path.isdir(src_path):
                    try:
                        os.mkdir(dest_path)
                    except Exception as err:
                        errmsg = 'failed to create directory {0}: {1}'.format(dest_path, err)
                        if not operation.processError(errmsg):
                            raise

                    # iterate over all files in source directory and copy it to dest
                    names = os.listdir(src_path)
                    for name in names:
                        src_filename = os.path.join(src_path, name)
                        do_add(src_filename, os.path.join(dest_path, name), remove_source, progress_increment)

                    try:
                        shutil.copystat(src_path, dest_path)

                        if remove_source:
                            os.rmdir(src_path)
                    except Exception as err:
                        errmsg = 'error while copying {0}: {1}'.format(source_basename, err)
                        if not operation.processError(errmsg):
                            raise
                else:
                    operation.setProgressText(tr('Copying {0}'.format(os.path.basename(src_path))))

                    try:
                        if remove_source:
                            shutil.move(src_path, dest_path)
                        else:
                            shutil.copy2(src_path, dest_path)
                    except Exception as err:
                        errmsg = 'failed to copy file {0}: {1}'.format(src_path, err)
                        if not operation.processError(errmsg):
                            raise

                    operation.setProgress(operation.state.progress + progress_increment)

            # count all files we should copy to provide correct progress values
            if os.path.isdir(source_filename):
                files_count = sum([len(e[2]) for e in os.walk(source_filename)])
            else:
                files_count = 1

            try:
                do_add(source_filename, absolute_dest_path, remove_source, 100 / files_count)
            except Exception as err:
                pass

    def getMeta(self, meta_name, default=None):
        return self.__config.get(meta_name, default)

    def setMeta(self, meta, value):
        self.__config[meta] = value

    def removeMeta(self, meta_name):
        self.__config = dict((key, self.__config[key]) for key in self.__config.keys() if meta_name != key)

    def testMeta(self, meta_name):
        return any((meta_name == key for key in self.__config.keys()))

    def __eq__(self, other):
        if not isinstance(other, LocalStorage):
            return NotImplemented

        return os.path.samefile(self.rootDirectory, other.rootDirectory)

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def isDirectoryStorage(path):
        return os.path.exists(path) and os.path.exists(os.path.join(path, LocalStorage.STORAGE_METADATA_FILENAME))
