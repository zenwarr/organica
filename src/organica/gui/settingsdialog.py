import logging
import copy
from PyQt4.QtCore import Qt, QAbstractListModel, QModelIndex
from PyQt4.QtGui import QListWidgetItem
from organica.gui.dialog import Dialog
from organica.utils.helpers import tr
from organica.utils.settings import globalSettings
from organica.utils.extend import globalObjectPool, globalPluginManager
from organica.gui.forms.ui_settingsdialog import Ui_SettingsDialog


logger = logging.getLogger(__name__)


class SettingsDialog(Dialog):
    PageProviderGroup = 'settings_page_provider'
    _PageRole = Qt.UserRole + 200
    _ProviderRole = Qt.UserRole + 201
    _IsInitedRole = Qt.UserRole + 202

    def __init__(self, parent):
        Dialog.__init__(self, parent, name='settings_dialog')

        self.ui = Ui_SettingsDialog()
        self.ui.setupUi(self)
        self.setWindowTitle(tr('Settings'))

        self.ui.lstPages.currentItemChanged.connect(self.__onCurrentPageItemChanged)

        self.__addStandardPages()

        with globalObjectPool().lock:
            for prov in globalObjectPool().objects(group=self.PageProviderGroup):
                self.__addPageFromProvider(prov)

            globalObjectPool().objectAdded.connect(self.__addPageFromProvider)
            globalObjectPool().objectRemoved.connect(self.__onObjectRemoved)

    def __addStandardPages(self):
        standard_pages = (
            (tr('General'), self.ui.pageGeneral),
            (tr('Extensions'), self.ui.pageExtensions)
        )

        for page in standard_pages:
            self.__addPage(page[0], page[1], None)

    def __addPageFromProvider(self, page_provider):
        if page_provider.group == self.PageProviderGroup:
            if not hasattr(page_provider, 'create') or not callable(page_provider.create):
                logger.error('provider should have "create" method')
                return

            try:
                page = page_provider.create(self)
            except Exception as err:
                logger.error('provider failed to create settings page: {0}'.format(err))
                return

            self.pagesStack.addWidget(page)

            page_name = page.title if hasattr(page, 'title') else tr('Unknown')
            self.__addPage(page_name, page, page_provider)

    def __addPage(self, page_name, page_widget, provider):
        item = QListWidgetItem(page_name)
        item.setData(self._PageRole, page_widget)
        item.setData(self._ProviderRole, provider)
        self.ui.lstPages.addItem(item)
        if not self.ui.lstPages.currentItem():
            self.ui.lstPages.setCurrentItem(item)

    def __onObjectRemoved(self, removed_object):
        if removed_object.group == self.PageProviderGroup:
            pages_list = self.ui.lstPages
            for row in range(pages_list.count()):
                item = pages_list.item(row)
                if item.data(self._ProviderRole) is removed_object:
                    if pages_list.currentRow() == row and pages_list.count() > 1:
                        new_row_to_select = row - 1 if row > 0 else row + 1
                        pages_list.setCurrentRow(new_row_to_select)

                    page = item.data(self._PageRole)
                    self.ui.pagesStack.removeWidget(page)
                    page.deleteLater()

                    pages_list.takeItem(row)
                    break

    def __onCurrentPageItemChanged(self, new_item):
        if new_item is None:
            self.ui.pagesStack.setCurrentIndex(-1)
        else:
            page = new_item.data(self._PageRole)
            if not new_item.data(self._IsInitedRole):
                # try to initialize page...
                if new_item.data(self._ProviderRole) is None:
                    self.__initStandardPage(page)
                else:
                    if not hasattr(page, 'init'):
                        logger.error('page {0} does not have "init" method'.format(new_item.text()))
                        return
                    else:
                        try:
                            page.init()
                        except Exception as err:
                            logger.error('page {0} failed to initialize: {1}'.format(new_item.text(), err))
                            return
                new_item.setData(self._IsInitedRole, True)
            self.ui.pagesStack.setCurrentWidget(page)

    def __initStandardPage(self, page):
        s = globalSettings()
        if page is self.ui.pageGeneral:
            quick_search = s['quick_search']
            if not isinstance(quick_search, bool):
                quick_search = True
            self.ui.chkQuickSearch.setChecked(quick_search)
        elif page is self.ui.pageExtensions:
            plugins_model = PluginsModel()
            self.ui.lstExtensions.setModel(plugins_model)

    def accept(self):
        pages_list = self.ui.lstPages
        for row in range(pages_list.count()):
            item = pages_list.item(row)
            page = item.data(self._PageRole)
            if item.data(self._IsInitedRole):
                if item.data(self._ProviderRole) is None:
                    self.__saveStandardPage(page)
                else:
                    if not hasattr(page, 'save'):
                        logger.error('page {0} does not have "save" method'.format(item.text()))
                        continue
                    else:
                        try:
                            page.save()
                        except Exception as err:
                            logger.error('page {0} failed to save changes: {1}'.format(item.text(), err))
                            continue
        Dialog.accept(self)

    def __saveStandardPage(self, page):
        s = globalSettings()
        if page is self.ui.pageGeneral:
            s['quick_search'] = self.ui.chkQuickSearch.isChecked()
        elif page is self.ui.pageExtensions:
            pass


class PluginsModel(QAbstractListModel):
    PluginInfoRole = Qt.UserRole + 200

    def __init__(self):
        QAbstractListModel.__init__(self)

        self.__pluginsInfo = []

        pm = globalPluginManager()
        self.__pluginsInfo = pm.allPlugins

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
        return None
