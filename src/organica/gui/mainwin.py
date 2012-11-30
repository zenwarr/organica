from organica.utils.singleton import Singleton
from organica.utils.settings import Settings, QuickSettings
from PyQt4 import QtCore, QtGui
from PyQt4.QtGui import QMainWindow, QStatusBar

class MainWindow(QMainWindow, Singleton):
	def __init__(self):
		QMainWindow.__init__(self)
		Singleton.__init__(self)

	def singleton_init(self):
		self.setAcceptDrops(True)

		self.statusBar().showMessage('Hello, World!')
		self.updateTitle()

		qs = QuickSettings()
		geom = qs.value('mainWindow/geometry')
		if geom is not None:
			self.restoreGeometry(geom)
		state = qs.value('mainWindow/state')
		if state is not None:
			self.restoreState(state)

	def closeEvent(self, closeEvent):
		qs = QuickSettings()
		qs.setValue('mainWindow/geometry', self.saveGeometry())
		qs.setValue('mainWindow/state', self.saveState())

	def updateTitle(self):
		self.setWindowTitle('Organica')
