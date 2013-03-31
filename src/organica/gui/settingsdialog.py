import logging
import copy
from PyQt4.QtCore import Qt, QAbstractListModel, QModelIndex
from PyQt4.QtGui import QListWidgetItem, QMessageBox, QDialogButtonBox
from organica.gui.dialog import Dialog
from organica.utils.helpers import tr
from organica.utils.settings import globalSettings
from organica.gui.selectionmodel import WatchingSelectionModel
from organica.utils.extend import globalObjectPool, globalPluginManager
from organica.gui.forms.ui_settingsdialog import Ui_SettingsDialog


logger = logging.getLogger(__name__)


class SettingsDialog(Dialog):
    PageProviderGroup = 'settings_page_provider'

    class _PageData(object):
        def __init__(self):
            self.title = ''
            self.topicItem = None
            self.page = None
            self.provider = None
            self.inited = False

    def __init__(self, parent):
        Dialog.__init__(self, parent, name='settings_dialog')

        self.__pages = []
        self.pluginsModel = PluginsModel()

        self.ui = Ui_SettingsDialog()
        self.ui.setupUi(self)
        self.setWindowTitle(tr('Settings'))

        self.ui.lstPages.currentItemChanged.connect(self.__onCurrentPageItemChanged)
        self.ui.btnPluginInfo.clicked.connect(self.__showPluginInfo)
        self.ui.btnPluginSettings.clicked.connect(self.__showPluginSettings)
        self.ui.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(self.__save)
        self.ui.buttonBox.button(QDialogButtonBox.RestoreDefaults).clicked.connect(self.__reset)

        self.__addStandardPages()

        with globalObjectPool().lock:
            for prov in globalObjectPool().objects(group=self.PageProviderGroup):
                self.__addPageFromProvider(prov)

            globalObjectPool().objectAdded.connect(self.__addPageFromProvider)
            globalObjectPool().objectRemoved.connect(self.__onObjectRemoved)

    def __addStandardPages(self):
        standard_pages = (
            (tr('General'), self.ui.pageGeneral),
            (tr('Plugins'), self.ui.pagePlugins)
        )

        for page in standard_pages:
            self.__addPage(page[0], page[1], None)

    def __addPageFromProvider(self, page_provider):
        if page_provider.group == self.PageProviderGroup:
            try:
                page = page_provider.create(self)
            except Exception as err:
                logger.error('provider failed to create settings page: {0}'.format(err))
                return

            page_name = page.title if hasattr(page, 'title') else tr('Unknown')

            self.pagesStack.addWidget(page)
            self.__addPage(page_name, page, page_provider)

    def __addPage(self, page_name, page_widget, provider):
        page_data = self._PageData()
        page_data.title = page_name
        page_data.page = page_widget
        page_data.provider = provider
        page_data.topicItem = QListWidgetItem(page_name)
        self.__pages.append(page_data)

        self.ui.lstPages.addItem(page_data.topicItem)
        if not self.ui.lstPages.currentItem():
            self.ui.lstPages.setCurrentItem(page_data.topicItem)

    def __onObjectRemoved(self, removed_object):
        if removed_object.group == self.PageProviderGroup:
            for page_data in self.__pages:
                if page_data.provider is removed_object:
                    pages_list = self.ui.lstPages
                    row = pages_list.row(page_data.topicItem)
                    if pages_list.currentItem() is page_data.topicItem and pages_list.count() > 1:
                        new_row_to_select = row - 1 if row > 0 else row + 1
                        pages_list.setCurrentRow(new_row_to_select)

                    self.ui.pagesStack.removeWidget(page_data.page)
                    page_data.page.deleteLater()

                    pages_list.takeItem(row)
                    break

    def __onCurrentPageItemChanged(self, new_item):
        if new_item is None:
            self.ui.pagesStack.setCurrentIndex(-1)
        else:
            page_data = self.__pages[self.ui.lstPages.row(new_item)]
            if not page_data.inited:
                # try to initialize page...
                if page_data.provider is None:
                    self.__initStandardPage(page_data)
                else:
                    try:
                        page_data.page.init()
                    except Exception as err:
                        logger.error('page {0} failed to initialize: {1}'.format(new_item.text(), err))
                        return
                page_data.inited = True
            self.ui.pagesStack.setCurrentWidget(page_data.page)

    def __initStandardPage(self, page_data):
        s = globalSettings()
        if page_data.page is self.ui.pageGeneral:
            self.ui.chkQuickSearch.setChecked(s['quick_search'])
        elif page_data.page is self.ui.pagePlugins:
            self.ui.lstPlugins.setModel(self.pluginsModel)
            selection_model = WatchingSelectionModel(self.pluginsModel)
            self.ui.lstPlugins.setSelectionModel(selection_model)
            selection_model.currentChanged.connect(self.__onCurrentPluginChanged)
            self.__onCurrentPluginChanged(self.ui.lstPlugins.currentIndex())

    def accept(self):
        self.__save()
        Dialog.accept(self)

    def __save(self):
        for page_data in self.__pages:
            if page_data.inited:
                if page_data.provider is None:
                    self.__saveStandardPage(page_data)
                else:
                    try:
                        page_data.page.save()
                    except Exception as err:
                        logger.error('page {0} failed to save changes: {1}'.format(page_data.title, err))
                        continue

    def __saveStandardPage(self, page_data):
        s = globalSettings()
        if page_data.page is self.ui.pageGeneral:
            s['quick_search'] = self.ui.chkQuickSearch.isChecked() == Qt.Checked
        elif page_data.page is self.ui.pagePlugins:
            self.pluginsModel.save()

    def __onCurrentPluginChanged(self, current_index):
        plugin_info = current_index.data(PluginsModel.PluginInfoRole)
        self.ui.btnPluginInfo.setEnabled(plugin_info is not None)
        has_settings_page = any(True for page_data in self.__pages if page_data.provider is not None and
                                                                page_data.provider.extensionUuid == plugin_info.uuid)
        self.ui.btnPluginSettings.setEnabled(has_settings_page)

    def __showPluginInfo(self):
        plugin_info = self.ui.lstPlugins.currentIndex().data(PluginsModel.PluginInfoRole)
        if plugin_info is not None:
            info_text = tr('{0}<br><br><b>Authors: </b>{1}').format(plugin_info.description, ', '.join(plugin_info.authors))
            msgbox = QMessageBox(self)
            msgbox.setWindowTitle(plugin_info.name)
            msgbox.setWindowIcon(plugin_info.icon)
            msgbox.setIcon(QMessageBox.Information)
            msgbox.setTextFormat(Qt.RichText)
            msgbox.setText(info_text)
            msgbox.exec_()

    def __showPluginSettings(self):
        plugin_info = self.ui.lstPlugins.currentIndex().data(PluginsModel.PluginInfoRole)
        for page_data in self.__pages:
            if page_data.provider is not None and page_data.provider.extensionUuid == plugin_info.uuid:
                self.ui.lstPages.setCurrentItem(page_data.topicItem)
                break

    def __reset(self):
        if QMessageBox.question(self, tr('Restore defaults'), tr('Do you really want to reset all application settings right now? '
                                'This action cannot be undone'), QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            globalSettings().reset()
            for page in self.__pages:
                page.inited = False
            self.__onCurrentPageItemChanged(self.ui.lstPages.currentItem())


class PluginsModel(QAbstractListModel):
    PluginInfoRole = Qt.UserRole + 200

    def __init__(self):
        QAbstractListModel.__init__(self)

        self.__pluginsInfo = []

        pm = globalPluginManager()
        with pm.lock:
            self.__pluginsInfo = copy.deepcopy(pm.allPlugins)

            pm.pluginLoaded.connect(self.__onPluginStateUpdated)
            pm.pluginUnloaded.connect(self.__onPluginStateUpdated)

    def save(self):
        for plugin_info in self.__pluginsInfo:
            globalPluginManager().enablePlugin(plugin_info, plugin_info.enabled)

    def rowCount(self, parent=QModelIndex()):
        return len(self.__pluginsInfo) if not parent.isValid() else 0

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self.__pluginsInfo)):
            return None

        plugin_info = self.__pluginsInfo[index.row()]
        if role == Qt.DisplayRole or role == Qt.EditRole:
            return plugin_info.name
        elif role == self.PluginInfoRole:
            return plugin_info
        elif role == Qt.CheckStateRole:
            return Qt.Checked if plugin_info.enabled else Qt.Unchecked
        elif role == Qt.BackgroundRole:
            return Qt.red if (not plugin_info.loaded and plugin_info.loadError is not None) else Qt.black
        elif role == Qt.ToolTipRole:
            if not plugin_info.loaded:
                if plugin_info.loadError is not None:
                    return tr('This plugin was not loaded due to error:\n{0}').format(plugin_info.loadError)
                else:
                    return tr('This plugin is not loaded')
            else:
                return tr('This plugin is loaded')
        elif role == Qt.DecorationRole:
            return plugin_info.icon
        return None

    def flags(self, index):
        if index.isValid() and index.column() == 0:
            return QAbstractListModel.flags(self, index) | Qt.ItemIsUserCheckable
        else:
            return QAbstractListModel.flags(self, index)

    def setData(self, index, value, role=Qt.DisplayRole):
        if role == Qt.CheckStateRole:
            self.__pluginsInfo[index.row()].enabled = bool(value == Qt.Checked)
            return True
        return False

    def __onPluginStateUpdated(self, plugin_info):
        for row in range(len(self.__pluginsInfo)):
            if self.__pluginsInfo[row].uuid == plugin_info.uuid:
                self.__pluginsInfo[row] = copy.deepcopy(plugin_info)
                self.dataChanged.emit(self.index(row, 0), self.index(row, 0))
                break
