import os

from PyQt4.QtGui import QWizard, QWizardPage, QLineEdit, QFormLayout, QLabel, \
                        QListView, QMessageBox, QVBoxLayout, QFileDialog, QCheckBox, QWidget
from PyQt4.QtCore import QFileInfo, pyqtProperty

from organica.utils.helpers import tr
from organica.gui.profiles import getProfile, genericProfile
from organica.gui.profilesmodel import ProfilesModel
from organica.lib.library import Library
from organica.gui.patheditwidget import PathEditWidget


class CreateLibraryWizard(QWizard):
    def __init__(self, parent):
        QWizard.__init__(self, parent)

        self.setWindowTitle(tr('Create library'))
        self.__lib = None

        for page_type in (LibraryNamePage, ProfilePage, DatabasePage, StoragePage):
            self.addPage(page_type(self))

    @property
    def lib(self):
        if self.__lib is None:
            self.__lib = self.__createLibrary()
        return self.__lib

    def __createLibrary(self):
        from organica.lib.storage import LocalStorage

        database_path = self.field('database_filename')
        if os.path.exists(database_path):
            os.remove(database_path)

        newlib = Library.createLibrary(database_path)
        newlib.name = self.field('library_name')
        newlib.setMeta('profile', self.field('profile_uuid'))

        if self.field('use_storage'):
            storage = LocalStorage.fromDirectory(self.field('storage_path'))
            storage.pathTemplate = self.field('path_template')
            try:
                storage.saveMetafile()
            except Exception as err:
                QMessageBox.warning(self, tr('Error'), tr('Failed to write storage metafile: {0}'.format(err)))
            newlib.storage = storage

        return newlib


class LibraryNamePage(QWizardPage):
    def __init__(self, parent):
        QWizardPage.__init__(self, parent)

        self.setTitle(tr('Library name'))
        self.setSubTitle(tr('Enter name for new library. Give name which describes objects ' \
                         'you will keep in this library'))

        self.nameEdit = QLineEdit(self)
        self.nameEdit.textChanged.connect(self.onTextChanged)

        layout = QFormLayout()
        layout.addRow(tr('Library name:'), self.nameEdit)
        self.setLayout(layout)

        self.registerField('library_name', self.nameEdit, 'text')

    def onTextChanged(self, new_text):
        self.completeChanged.emit()

    def isComplete(self):
        return bool(self.nameEdit.text())


class ProfilePage(QWizardPage):
    def __init__(self, parent):
        QWizardPage.__init__(self, parent)

        self.setTitle(tr('Profile'))
        self.setSubTitle(tr('Select profile which will be used to manage objects in this library'))

        self.label = QLabel(self)
        self.label.setWordWrap(True)
        self.label.setText(tr('Profile:'))

        self.profilesModel = ProfilesModel()

        self.profileList = QListView(self)
        self.profileList.setModel(self.profilesModel)

        # let generic profile be selected by default
        generic_profile = genericProfile()
        if generic_profile is not None:
            self.profileList.setCurrentIndex(self.profilesModel.profileIndex(generic_profile))

        if not self.profilesModel.rowCount():
            QMessageBox.information(self, tr('Creating library'),
                    tr('You have no profiles installed. Although you can still create '
                    'libraries, it is better to install extensions providing profiles you need'))

        self.registerField('profile_uuid', self, 'profileUuid')

        layout = QVBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.profileList)
        self.setLayout(layout)

    @pyqtProperty(str)
    def profileUuid(self):
        cindex = self.profileList.currentIndex()
        return cindex.data(ProfilesModel.ProfileRole).uuid if cindex.isValid() else ''


class DatabasePage(QWizardPage):
    def __init__(self, parent):
        QWizardPage.__init__(self, parent)

        self.setTitle(tr('Database'))
        self.setSubTitle(tr('Select where library database file will be located'))

        self.pathEdit = PathEditWidget(self)
        self.pathEdit.pathChanged.connect(self.__onPathChanged)
        self.pathEdit.fileDialog.setFileMode(QFileDialog.AnyFile)
        self.pathEdit.fileDialog.setNameFilters(['Organica library files (*.orl)'])

        self.registerField('database_filename', self, 'databaseFilename')

        layout = QFormLayout()
        layout.addRow(tr('Database file:'), self.pathEdit)
        self.setLayout(layout)

    @pyqtProperty(str)
    def databaseFilename(self):
        return self.pathEdit.path

    def isComplete(self):
        return bool(self.pathEdit.path)

    def validatePage(self):
        if QFileInfo(self.databaseFilename).exists():
            answer_button = QMessageBox.question(self, tr('Database file exists'),
                     tr('Choosen database file already exist and can be used by another library. '
                     'Replacing it will cause loss of information stored in existing database.\n\n'
                     'Do you really want to replace existing database file?'),
                     QMessageBox.Yes | QMessageBox.No)
            return answer_button == QMessageBox.Yes
        return True

    def __onPathChanged(self, new_path):
        self.completeChanged.emit()


class StoragePage(QWizardPage):
    def __init__(self, parent):
        QWizardPage.__init__(self, parent)

        self.setTitle(tr('Local storage'))
        self.setSubTitle(tr('Storage is local folder where all files you add to library will be stored. ' \
                            'You can create storage for this library by checking box below.'))

        self.chkUseStorage = QCheckBox(tr('Use storage'), self)
        self.chkUseStorage.clicked.connect(self.completeChanged)

        self.storageWidget = QWidget(self)
        self.storageWidget.hide()
        self.chkUseStorage.toggled.connect(self.storageWidget.setVisible)

        self.pathEdit = PathEditWidget(self)
        self.pathEdit.fileDialog.setFileMode(QFileDialog.Directory)
        self.pathEdit.pathChanged.connect(self.completeChanged)

        self.pathTemplateEdit = QLineEdit(self)
        self.pathTemplateEdit.textChanged.connect(self.completeChanged)

        self.registerField('use_storage', self, 'useStorage')
        self.registerField('storage_path', self, 'storagePath')
        self.registerField('path_template', self, 'pathTemplate')

        layout = QFormLayout(self.storageWidget)
        layout.addRow(tr('Storage directory:'), self.pathEdit)
        layout.addRow(tr('Path template:'), self.pathTemplateEdit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.chkUseStorage)
        layout.addWidget(self.storageWidget)

    @pyqtProperty(bool)
    def useStorage(self):
        return self.chkUseStorage.isChecked()

    @pyqtProperty(str)
    def storagePath(self):
        return self.pathEdit.path

    @pyqtProperty(str)
    def pathTemplate(self):
        return self.pathTemplateEdit.text()

    def isComplete(self):
        return bool(not self.chkUseStorage.isChecked() or (self.pathEdit.path and self.pathTemplateEdit.text()))

    def validatePage(self):
        from organica.lib.storage import LocalStorage

        # check if storage directory choosen is storage already
        if LocalStorage.isDirectoryStorage(self.pathEdit.path):
            ans = QMessageBox.question(self, tr('Directory is storage'), tr('It seems like choosen directory already '
                             'used as storage. Old parameters will be imported (remove meta.storage file to '
                             'reset storage parameters). Really use this directory?'),
                             QMessageBox.Yes | QMessageBox.No)
            return ans != QMessageBox.No
        else:
            return True
