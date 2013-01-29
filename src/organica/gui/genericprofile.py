from PyQt4.QtGui import QComboBox

from organica.lib.tagclassesmodel import TagClassesModel
from organica.lib.filters import TagQuery
from organica.utils.extend import globalObjectPool


GENERIC_PROFILE_UUID = '7c73bb70-6720-11e2-bcfd-0800200c9a66'


class TopicNameCombo(QComboBox):
    def __init__(self, environ, parent):
        QComboBox.__init__(self, parent)

        self.environ = environ

        model = TagClassesModel()
        model.showSpecialClass = True
        model.specialClassName = '*'
        model.lib = environ.lib
        self.setModel(model)
        self.setModelColumn(0)

        self.editTextChanged.connect(self.__onEditTextChanged)

        if environ.lib is not None:
            saved_filter_index = self.findText(environ.lib.getMeta('ui_tagclassfilter', '*'))
            if saved_filter_index != -1:
                self.setCurrentIndex(saved_filter_index)

    def onUnload(self):
        if self.environ.lib is not None:
            topic_filter = self.currentText()
            self.environ.lib.setMeta('ui_tagclassfilter', topic_filter)
            self.model().lib = None

    def __onEditTextChanged(self, class_name):
        if self.environ and self.environ.lib is not None:
            topics_model = self.environ.ui.topicsView.model()

            # save current item
            current_tag = self.environ.ui.topicsView.selectedTag

            existing_filter = topics_model.filter
            existing_filter = existing_filter.disableHinted(self.filterHint)

            if class_name != '*':
                class_filter = TagQuery(tag_class=class_name)
                class_filter.setHint(self.filterHint)
                existing_filter = existing_filter & class_filter

            topics_model.filter = existing_filter

            if current_tag:
                indexes = topics_model.indexes(current_tag)
                if indexes:
                    self.environ.ui.topicsView.setCurrentIndex(indexes[0])


class GenericProfile(object):
    extensionUuid = ''
    group = 'profile'
    name = 'Generic profile'
    description = 'Can be used with any library, but provides only most common functions to ' \
                  'manage classes, tags and nodes'
    uuid = GENERIC_PROFILE_UUID

    def onLoad(self, environ):
        self.topicWidget = TopicNameCombo(environ, environ.ui)
        environ.ui.topicsView.layout().addWidget(self.topicWidget)

    def onUnload(self):
        self.topicWidget.onUnload()


def registerProfile():
    # register generic profile
    _genericProfile = GenericProfile()
    globalObjectPool().add(_genericProfile)
