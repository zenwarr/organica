import os
from PyQt4.QtCore import QUrl

class Locator(object):
    MANAGED_FILES_SCHEME = 'storage'

    def __init__(self, url = ''):
        self.__url = QUrl(url)
        self.__storage = None

    @staticmethod
    def url(url):
        return Locator(url)

    @staticmethod
    def localFile(file_path):
        return Locator(QUrl.fromLocalFile(file_path))

    @staticmethod
    def managedFile(file_path, storage):
        l = Locator(QUrl(self.MANAGED_FILES_SCHEME + '//' + file_path))
        l.__storage = storage
        return l

    @property
    def isLocalFile(file_path):
        return self.__url.isLocalFile()

    @property
    def isStorageFile(file_path):
        return self.scheme().casefold() == self.MANAGED_FILES_SCHEME.casefold()

    @property
    def url(self):
        return self.__url

    @property
    def storage(self):
        return self.__storage

    @property
    def localFilePath(self):
        path = None
        if self.__url.isLocalFile():
            path = self.__url.toLocalFile()
        elif self.isStorageFile:
            path = self.__url.path()

        return path

    def databaseForm(self):
        return self.url.toString()
