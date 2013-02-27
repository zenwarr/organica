from PyQt4.QtCore import QByteArray
from PyQt4.QtGui import QDialog
from organica.utils.settings import globalQuickSettings


class Dialog(QDialog):
    """Dialog that remembers its position"""

    def __init__(self, parent=None, name=''):
        QDialog.__init__(self, parent)
        self.name = name
        if self.name:
            qs = globalQuickSettings()
            saved_geom = qs[self.name + '_geometry']
            if saved_geom and isinstance(saved_geom, str):
                self.restoreGeometry(QByteArray.fromHex(saved_geom))

    def closeEvent(self, close_event):
        if self.name:
            qs = globalQuickSettings()
            qs[self.name + '_geometry'] = str(self.saveGeometry().toHex(), encoding='ascii')
