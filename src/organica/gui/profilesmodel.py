from PyQt4.QtGui import QStandardItemModel, QStandardItem
from PyQt4.QtCore import Qt, QModelIndex
from organica.utils.extend import globalObjectPool
from organica.utils.helpers import tr


class ProfilesModel(QStandardItemModel):
    ProfileRole = Qt.UserRole + 200
    ProfileUuidRole = Qt.UserRole + 201

    def __init__(self, show_default=True):
        QStandardItemModel.__init__(self)

        self.setColumnCount(1)

        if show_default:
            self.appendRow(QStandardItem(tr('Default profile')))

        with globalObjectPool().lock:
            all_profiles = globalObjectPool().objects(group='profile')
            for profile in all_profiles:
                self.appendRow(self.__createItemForProfile(profile))

            globalObjectPool().objectAdded.connect(self.__objectAdded)
            globalObjectPool().objectRemoved.connect(self.__objectRemoved)

    def __createItemForProfile(self, profile):
        item = QStandardItem()
        item.setText(profile.name)
        if hasattr(profile, 'icon'):
            item.setIcon(profile.icon)
        if hasattr(profile, 'description'):
            item.setToolTip(profile.description)
        item.setData(profile, self.ProfileRole)
        if hasattr(profile, 'uuid'):
            item.setData(profile.uuid, self.ProfileUuidRole)
        return item

    def __objectAdded(self, new_object):
        if new_object.group == 'profile':
            self.appendRow(self.__createItemForProfile(new_object))

    def __objectRemoved(self, removed_object):
        if removed_object.group == 'profile':
            index = self.profileIndex(removed_object)
            if index.isValid():
                self.removeRows(index.row(), 1)

    def profileIndex(self, profile):
        for row_index in range(self.rowCount()):
            if isinstance(profile, str):
                if self.index(row_index, 0).data(self.ProfileUuidRole) == profile:
                    return self.index(row_index, 0)
            else:
                if self.index(row_index, 0).data(self.ProfileRole) is profile:
                    return self.index(row_index, 0)
        return QModelIndex()

    def addUnknownProfile(self, profile_uuid, profile_name=None):
        if not self.profileIndex(profile_uuid).isValid():
            item = QStandardItem()
            item.setText(profile_name or profile_uuid)
            item.setData(profile_uuid, self.ProfileUuidRole)
            self.appendRow(item)

    def removeUnknownProfile(self, profile_uuid):
        index = self.profileIndex(profile_uuid)
        if index.isValid() and index.data(self.ProfileRole) is None:
            self.removeRows(index.row(), 1)
