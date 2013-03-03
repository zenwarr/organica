import os
from PyQt4.QtCore import QUrl, QDir, QFileInfo
from PyQt4.QtGui import QFileIconProvider
from organica.utils.helpers import cicompare


class Locator(object):
    MANAGED_FILES_SCHEME = 'storage'

    def __init__(self, url=''):
        self.__url = QUrl(url)
        self.__lib = None

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
        return self.__url.toString()

    @staticmethod
    def fromUrl(url, lib=None):
        url = QUrl(url)
        if cicompare(url.scheme(), Locator.MANAGED_FILES_SCHEME):
            return Locator.fromManagedFile(url.toLocalFile(), lib)
        else:
            return Locator(url)

    @staticmethod
    def fromLocalFile(path):
        return Locator(QUrl.fromLocalFile(path))

    @staticmethod
    def fromManagedFile(path, lib):
        if not os.path.isabs(path):
            # assume that directory already relative to storage root
            rel_path = path
        elif lib is not None and lib.storage is not None and lib.storage.rootDirectory:
            rel_path = QDir(lib.storage.rootDirectory).relativeFilePath(path)
        else:
            return None

        loc = Locator(Locator.MANAGED_FILES_SCHEME + '://' + rel_path)
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
        cp = Locator(self.__url)
        cp.__lib = self.__lib  # do not deepcopy librar
        return cp

    def __eq__(self, other):
        return isinstance(other, Locator) and self.__url == other.__url
