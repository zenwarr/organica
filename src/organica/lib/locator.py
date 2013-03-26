import os
from PyQt4.QtCore import QUrl, QDir, QFileInfo
from PyQt4.QtGui import QFileIconProvider
from organica.utils.helpers import cicompare


class Locator(object):
    MANAGED_FILES_SCHEME = 'storage'

    def __init__(self, url='', source_url=None):
        self.__lib = None
        self.__sourceUrl = source_url
        if isinstance(url, str) and url and (QUrl(url).scheme() in ('file', '')):
            self.__url = QUrl.fromLocalFile(url)
        else:
            self.__url = QUrl(url)

    @property
    def lib(self):
        return self.__lib if self.isManagedFile else None

    @property
    def url(self):
        return QUrl(self.__url)

    @property
    def launchUrl(self):
        """Same as url, but translates storage scheme to file"""
        if self.isLocalFile:
            return QUrl.fromLocalFile(self.localFilePath)
        else:
            return self.url

    @property
    def isLocalFile(self):
        return self.isManagedFile or self.__url.isLocalFile()

    @property
    def isManagedFile(self):
        return cicompare(self.__url.scheme(), self.MANAGED_FILES_SCHEME)

    @property
    def localFilePath(self):
        if self.isManagedFile:
            if self.__lib is not None and self.__lib.storage is not None and self.__lib.storage.rootDirectory:
                return os.path.join(self.__lib.storage.rootDirectory, self.__url.path())
        elif self.isLocalFile:
            return self.__url.toLocalFile()
        return ''

    @property
    def databaseForm(self):
        return str(self)

    def __str__(self):
        if self.__url.isLocalFile():
            return self.__url.toLocalFile()
        return self.__url.toString()

    @staticmethod
    def fromUrl(url, lib=None, source_url=None):
        url = QUrl(url)
        if cicompare(url.scheme(), Locator.MANAGED_FILES_SCHEME):
            return Locator.fromManagedFile(url.path(), lib, source_url)
        else:
            return Locator(url, source_url)

    @staticmethod
    def fromLocalFile(path, source_url=None):
        return Locator(QUrl.fromLocalFile(path), source_url)

    @staticmethod
    def fromManagedFile(path, lib, source_url=None):
        if not os.path.isabs(path):
            # assume that directory already relative to storage root
            rel_path = path
        elif lib is not None and lib.storage is not None and lib.storage.rootDirectory:
            rel_path = QDir(lib.storage.rootDirectory).relativeFilePath(path)
        else:
            return None

        managed_file_url = QUrl()
        managed_file_url.setScheme('storage')
        managed_file_url.setPath(rel_path)
        loc = Locator(managed_file_url, source_url)
        loc.__lib = lib
        return loc

    @staticmethod
    def fromDatabaseForm(db_form, lib):
        return Locator.fromUrl(db_form, lib)

    @property
    def icon(self):
        if self.isLocalFile:
            return QFileIconProvider().icon(QFileInfo(self.localFilePath))
        else:
            return None

    def __deepcopy__(self, memo):
        # it is impossible to deepcopy PyQt objects
        cp = Locator(self.__url, self.__sourceUrl)
        cp.__lib = self.__lib  # do not deepcopy library
        return cp

    def __eq__(self, other):
        if not isinstance(other, Locator):
            return NotImplemented

        return self.__url == other.__url

    @property
    def sourceUrl(self):
        return self.__sourceUrl

    def resolveLocalFilePath(self, node):
        if not self.isManagedFile or node.lib.storage is None:
            return self.localFilePath
        else:
            return node.lib.storage.getStoragePath(self.sourceUrl.toString(), node)
