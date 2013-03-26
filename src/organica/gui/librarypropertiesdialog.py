from PyQt4.QtCore import QFileInfo
from PyQt4.QtGui import QFileDialog
from organica.gui.dialog import Dialog
from organica.gui.forms.ui_librarypropertiesdialog import Ui_LibraryPropertiesDialog
from organica.gui.profilesmodel import ProfilesModel
from organica.utils.helpers import tr, formatSize


class LibraryPropertiesDialog(Dialog):
    def __init__(self, parent, lib):
        Dialog.__init__(self, parent, name='library_properties_dialog')
        self.lib = lib
        self.setWindowTitle(tr('Library properties'))

        self.ui = Ui_LibraryPropertiesDialog()
        self.ui.setupUi(self)

        self.profilesModel = ProfilesModel(show_default=True)
        self.ui.cmbProfiles.setModel(self.profilesModel)
        self.ui.storageRootDirectory.fileDialog.setFileMode(QFileDialog.Directory)

        self.__load()

    def accept(self):
        self.__save()
        Dialog.accept(self)

    def __load(self):
        from organica.gui.profiles import getProfile

        if self.lib is not None:
            self.ui.libraryDatabase.setText(self.lib.databaseFilename)

            self.ui.txtLibraryName.setText(self.lib.name)

            profile_uuid = self.lib.profileUuid
            if not profile_uuid:
                self.ui.cmbProfiles.setCurrentIndex(0)
            else:
                profile = getProfile(profile_uuid)
                if not profile:
                    self.ui.cmbProfiles.model().addUnknownProfile(profile_uuid)
                self.ui.cmbProfiles.setCurrentIndex(self.profilesModel.profileIndex(profile_uuid).row())

            # load storage information
            storage_used = self.lib.storage is not None
            self.ui.chkUseStorage.setChecked(storage_used)
            if storage_used:
                storage = self.lib.storage

                self.ui.storageRootDirectory.path = storage.rootDirectory
                self.ui.txtStoragePathTemplate.setText(storage.pathTemplate)

            stat = self.lib.calculateStatistics()
            self.ui.lblClasses.setText(str(stat.classesCount))
            self.ui.lblTags.setText(str(stat.tagsCount))
            self.ui.lblNodes.setText(str(stat.nodesCount))
            self.ui.lblDatabaseSize.setText(str(formatSize(stat.databaseSize)))

    def __save(self):
        from organica.lib.storage import LocalStorage

        if self.lib is not None:
            self.lib.name = self.ui.txtLibraryName.text()

            profile_uuid = self.profilesModel.index(self.ui.cmbProfiles.currentIndex(), 0).data(ProfilesModel.ProfileUuidRole)
            if not profile_uuid:
                # we should assign 'default' profile for library - this means that library will always be opened with
                # profile installed as default (default profiles can differ on different application instances)
                self.lib.profileUuid = None
            else:
                self.lib.profileUuid = profile_uuid

            storage_used = self.ui.chkUseStorage.isChecked()
            if self.lib.storage is not None and not storage_used:
                self.lib.storage = None
            if storage_used:
                storage_root = self.ui.storageRootDirectory.path
                if self.lib.storage is None or QFileInfo(self.lib.storage.rootDirectory) != QFileInfo(storage_root):
                    self.lib.storage = LocalStorage.fromDirectory(storage_root)

            if storage_used:
                self.lib.storage.pathTemplate = self.ui.txtStoragePathTemplate.text()
