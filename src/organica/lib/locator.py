import os
import copy
from PyQt4.QtCore import QUrl, QDir, QFileInfo
from PyQt4.QtGui import QFileIconProvider, QIcon
from organica.utils.helpers import cicompare
from organica.lib.objects import ObjectError


class LocatorResolveError(ObjectError):
    pass


class Locator(object):
    ManagedFilesScheme = 'storage'

    def __init__(self, url='', source=''):
        """Equivalent to Locator.fromUrl. Objects of this class are immutable"""
        if isinstance(url, Locator):
            other_locator = url
            self.__url = other_locator.__url
            self.__source = other_locator.__source
        else:
            if not url:
                self.__url = QUrl()
            elif isinstance(url, str) and url and not QUrl(url).scheme():
                self.__url = QUrl.fromLocalFile(url)
            else:
                self.__url = QUrl(url)
            self.__source = Locator(source) if source else None

    def getResolved(self, node):
        """Resolves URL this locator points to. Same locator can be resolved to different URLs depending on which node
        it is linked with. Return value is Locator object that cannot have ManagedFilesScheme."""
        if self.__url.scheme() != self.ManagedFilesScheme:
            return copy.deepcopy(self)
        else:
            if node is None or node.lib is None:
                raise LocatorResolveError()
            storage = node.lib.storage  # store reference to storage here to not lock library
            if storage is None:
                raise LocatorResolveError()
            else:
                return Locator(os.path.join(storage.rootDirectory, self.__url.path()))

    @property
    def url(self) -> QUrl:
        """Return QUrl object representing resource URL."""
        return QUrl(self.__url)

    @property
    def source(self):
        return Locator(self.__source or '')

    @property
    def isLocalFile(self) -> bool:
        """True if url has file: scheme"""
        return self.__url.isLocalFile()

    @property
    def isManagedFile(self) -> bool:
        """True if url has scheme: scheme"""
        return self.__url.scheme() == self.ManagedFilesScheme

    @property
    def localFilePath(self) -> str:
        """Return local file path. Does not resolves locator, of course."""
        return self.__url.toLocalFile() if self.isLocalFile else ''

    @property
    def databaseForm(self) -> str:
        return str(self)

    @property
    def icon(self):
        if self.isLocalFile:
            target_file_info = QFileInfo(self.localFilePath)
            if not target_file_info.exists():
                # check if we can use source file... we will use source if it does not exist - some systems can determine
                # file type by extension
                if self.source and self.source.isLocalFile:
                    target_file_info = QFileInfo(self.source.localFilePath)
            return QFileIconProvider().icon(target_file_info)
        else:
            return QIcon()

    @property
    def broken(self) -> bool:
        """URL with storage: scheme is not considered to be broken"""
        return self.isLocalFile and not os.path.exists(self.localFilePath)

    def __str__(self):
        return self.localFilePath if self.isLocalFile else self.__url.toString()

    def __deepcopy__(self, memo):
        return Locator(self.__url, self.__source)

    def __eq__(self, other):
        if not isinstance(other, Locator):
            return NotImplemented
        return self.__url == other.__url  # source does not sense

    def __ne__(self, other):
        r = self.__eq__(other)
        return not r if r != NotImplemented else r

    def __bool__(self):
        return bool(str(self))

    @staticmethod
    def fromUrl(url):
        return Locator(url)

    @staticmethod
    def fromLocalFile(path, source=None):
        return Locator(path, source)

    @staticmethod
    def fromManagedFile(path, lib, source=None):
        if not os.path.isabs(path):
            # assume that path already relative to storage root
            rel_path = path
        elif lib is not None:
            storage = lib.storage
            with storage.lock:
                if not storage.rootDirectory:
                    raise LocatorResolveError('no storage')
                rel_path = QDir(storage.rootDirectory).relativeFilePath(path)
        else:
            raise LocatorResolveError('no library')

        rel_path = os.path.normcase(os.path.normpath(rel_path))

        managed_file_url = QUrl()
        managed_file_url.setScheme(Locator.ManagedFilesScheme)
        managed_file_url.setPath(rel_path)
        return Locator(managed_file_url, source)

    @staticmethod
    def fromDatabaseForm(db_form):
        return Locator(db_form)

