from PyQt4.QtGui import QComboBox

from organica.lib.tagclassesmodel import TagClassesModel
from organica.lib.filters import TagQuery, replaceInFilters
from organica.utils.extend import globalObjectPool
from organica.generic.extension import GENERIC_EXTENSION_UUID


GenericProfileUuid = '7c73bb70-6720-11e2-bcfd-0800200c9a66'


class TopicNameCombo(QComboBox):
    filterHint = 'class_name_filter'

    def __init__(self, environ, parent):
        QComboBox.__init__(self, parent)

        self.environ = environ

        model = TagClassesModel()
        model.showSpecialClass = True
        model.specialClassName = '*'
        model.lib = environ.lib
        self.setModel(model)
        self.setModelColumn(0)

        self.currentIndexChanged[str].connect(self.__onClassChanged)

        if environ.lib is not None:
            saved_filter_index = self.findText(environ.lib.getMeta('ui_tagclassfilter', '*'))
            if saved_filter_index != -1:
                self.setCurrentIndex(saved_filter_index)

    def onUnload(self):
        if self.environ.lib is not None:
            topic_filter = self.currentText()
            self.environ.lib.setMeta('ui_tagclassfilter', topic_filter)
            self.model().lib = None

    def __onClassChanged(self, class_name):
        from organica.lib.tagsmodel import TagsModel

        if self.environ and self.environ.lib is not None:
            topics_view = self.environ.ui.topicsView
            topics_model = topics_view.model

            # save current item
            current_tag = topics_view.currentTag

            class_filter = TagQuery(tag_class=class_name) if class_name != '*' else TagQuery()
            class_filter.hint = self.filterHint
            topics_model.filters = replaceInFilters(topics_model.filters, self.filterHint, class_filter)

            topics_view.currentTag = current_tag


class GenericProfileEnviron(object):
    def __init__(self, environ):
        self.libEnviron = environ
        self.topicWidget = TopicNameCombo(environ, environ.ui)
        environ.ui.topicsView.layout().addWidget(self.topicWidget)

    def onUnload(self):
        self.topicWidget.onUnload()


class GenericProfile(object):
    extensionUuid = GENERIC_EXTENSION_UUID
    group = 'profile'
    name = 'Generic profile'
    description = 'Can be used with any library, but provides only most common functions to ' \
                  'manage classes, tags and nodes'
    uuid = GenericProfileUuid

    def createProfileEnviron(self, environ):
        return GenericProfileEnviron(environ)
