from PyQt4.QtGui import QDialog, QVBoxLayout, QTabWidget, QPushButton, QLabel, QTextBrowser
from PyQt4.QtCore import QCoreApplication, QFile, Qt

from organica.utils.helpers import tr
import organica.gui.resources.qrc_main


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        QDialog.__init__(self, parent)

        self.resize(500, 500)
        self.setWindowTitle(tr('About program'))

        layout = QVBoxLayout(self)

        self.label = QLabel(self)
        self.label.setTextFormat(Qt.RichText)
        self.label.setText(tr('Organica version {0}, (c) 2013 zenwarr<br>' \
                            '<a href="http://github.org/zenwarr/organica">http://github.org/zenwarr/organica</a>') \
                            .format(QCoreApplication.applicationVersion()))

        self.tabWidget = QTabWidget(self)
        self.copyingText = QTextBrowser(self)
        self.tabWidget.addTab(self.copyingText, tr('License'))
        self.creditsText = QTextBrowser(self)
        self.tabWidget.addTab(self.creditsText, tr('Credits'))

        l_file = QFile(':/main/data/COPYING.html')
        if l_file.open(QFile.ReadOnly | QFile.Text):
            self.copyingText.setText(str(l_file.readAll(), encoding='utf-8'))

        c_file = QFile(':/main/data/CREDITS.html')
        if c_file.open(QFile.ReadOnly | QFile.Text):
            self.creditsText.setText(str(c_file.readAll(), encoding='utf-8'))

        self.okButton = QPushButton(tr('OK'), self)
        self.okButton.clicked.connect(self.close)
        self.okButton.setDefault(True)

        layout.addWidget(self.label)
        layout.addWidget(self.tabWidget)
        layout.addWidget(self.okButton)
