import os
from PyQt4.QtGui import QFileDialog, QMessageBox, QDialogButtonBox, QPushButton
from organica.gui.dialog import Dialog
from organica.gui.profilesmodel import ProfilesModel
from organica.lib.storage import LocalStorage
from organica.utils.helpers import tr, formatSize
from organica.utils.operations import globalOperationContext, OperationState
from organica.gui.forms.ui_librarypropertiesdialog import Ui_LibraryPropertiesDialog
from organica.gui.forms.ui_changestoragedialog import Ui_ChangeStorageDialog


class LibraryPropertiesDialog(Dialog):
    def __init__(self, parent, lib):
        Dialog.__init__(self, parent, name='library_properties_dialog')
        self.lib = lib
        self.setWindowTitle(tr('Library properties'))

        self.ui = Ui_LibraryPropertiesDialog()
        self.ui.setupUi(self)
        self.storage = None

        self.profilesModel = ProfilesModel(show_default=True)
        self.ui.cmbProfiles.setModel(self.profilesModel)
        self.ui.btnChangeRootDirectory.clicked.connect(self.__changeRootDirectory)

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

            self.ui.chkAutoDeleteUnusedTags.setChecked(self.lib.autoDeleteUnusedTags)

            # load storage information
            storage_used = self.lib.storage is not None
            self.ui.chkUseStorage.setChecked(storage_used)
            if storage_used:
                self.__loadStorageParameters(self.lib.storage)
            self.storage = self.lib.storage

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

            self.lib.autoDeleteUnusedTags = self.ui.chkAutoDeleteUnusedTags.isChecked()

            storage_used = self.ui.chkUseStorage.isChecked()
            if self.lib.storage is not None and not storage_used:
                self.lib.storage = None
            if storage_used:
                self.lib.storage = self.storage

            if storage_used:
                self.lib.storage.pathTemplate = self.ui.txtStoragePathTemplate.text()

    def __changeRootDirectory(self):
        dialog = ChangeStorageDialog(self, self.storage, self.ui.storageRootDirectory.text())
        if dialog.exec_() == ChangeStorageDialog.Accepted:
            self.__loadStorageParameters(dialog.storage)
            self.storage = dialog.storage

    def __loadStorageParameters(self, storage):
        self.ui.storageRootDirectory.setText(storage.rootDirectory if storage else '')
        self.ui.storageRootDirectory.setToolTip(storage.rootDirectory if storage else '')
        self.ui.txtStoragePathTemplate.setText(storage.pathTemplate if storage else '')


class ChangeStorageDialog(Dialog):
    def __init__(self, parent, actual_storage, storage):
        Dialog.__init__(self, parent, name='change_storage_dialog')
        self.setWindowTitle(tr('Change storage'))
        self.actualStorage = actual_storage
        self.__storage = storage

        self.ui = Ui_ChangeStorageDialog()
        self.ui.setupUi(self)
        self.loadGeometry()

        self.ui.widgetStack.setCurrentIndex(0)

        self.createButton = QPushButton(tr('Initialize storage'))
        self.ui.buttonBox.addButton(self.createButton, QDialogButtonBox.AcceptRole)

        self.ui.rootDirectory.fileDialog.setFileMode(QFileDialog.Directory)
        self.ui.rootDirectory.pathChanged.connect(self.__onPathChanged)
        self.__onPathChanged(self.ui.rootDirectory.path)

        self.ui.chkCopySettings.setEnabled(self.actualStorage is not None)
        if self.actualStorage is not None:
            self.ui.chkCopySettings.setChecked(True)

        self.ui.chkCopyFiles.setEnabled(self.actualStorage is not None)
        self.ui.chkMoveFiles.setEnabled(self.actualStorage is not None)
        self.ui.chkDoNothing.setChecked(True)

        if self.actualStorage is not None:
            self.ui.rootDirectory.path = self.actualStorage.rootDirectory

    def accept(self):
        from organica.utils.fileop import removeFile, copyFile, isSameFile

        if (self.storage is None and self.actualStorage is None) or self.storage == self.actualStorage:
            Dialog.accept(self)

        root_path = self.ui.rootDirectory.path
        try:
            if not os.path.exists(root_path):
                os.makedirs(root_path, exist_ok=True)
            self.__storage = LocalStorage.fromDirectory(root_path)
        except Exception as err:
            QMessageBox.information(self, tr('Error'), tr('Failed to initialize storage in {0} directory: {1}')
                                    .format(root_path, err))
            return

        with globalOperationContext().newOperation('initializing storage') as op:
            op.progressChanged.connect(self.__updateOperationProgress)
            op.progressTextChanged.connect(self.__updateOperationProgressText)
            op.finished.connect(self.__onOperationFinished)

            self.ui.widgetStack.setCurrentIndex(1)

            if self.ui.chkRemoveFiles.isChecked():
                self.storage.removeAllFiles()

            if self.actualStorage is not None:
                if self.ui.chkCopyFiles.isChecked():
                    self.storage.importFilesFrom(self.actualStorage)
                elif self.ui.chkMoveFiles.isChecked():
                    self.storage.importFilesFrom(self.actualStorage, remove_source=True)

            if self.actualStorage is not None and self.ui.chkCopySettings.isChecked():
            # copy settings from one storage to another
                self.storage.copySettingsFrom(self.actualStorage)

    def __updateOperationProgress(self, progress_value):
        self.ui.operationProgress.setValue(int(progress_value))

    def __updateOperationProgressText(self, progress_text):
        self.ui.lblProgressText.setText(progress_text)

    def __onOperationFinished(self, finish_status):
        if finish_status != OperationState.COMPLETED:
            QMessageBox.information(self, tr('Error'), tr('Operation was not completed successfully'))
        Dialog.accept(self)

    def __onPathChanged(self, new_path):
        new_storage = LocalStorage.fromDirectory(new_path)
        self.createButton.setEnabled(new_storage is not None and new_storage != self.actualStorage)

    @property
    def storage(self):
        return self.__storage
