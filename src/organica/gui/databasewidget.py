import sqlite3
from PyQt4.QtGui import QWidget, QComboBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QToolButton, \
                        QDialog
from organica.utils.helpers import tr


class DatabaseWidget(QWidget):
    def __init__(self, db_connection=None, parent=None):
        QWidget.__init__(self, parent)
        self.connection = db_connection

        self.tableSelectCombo = QComboBox(self)
        self.tableSelectCombo.currentIndexChanged[str].connect(self.changeTable)
        self.updateTableButton = QToolButton(self)
        self.updateTableButton.setText(tr('Update data'))
        self.updateTableButton.clicked.connect(self.fillData)
        self.dataWidget = QTableWidget(self)

        self.primaryLayout = QVBoxLayout(self)
        self.primaryLayout.setContentsMargins(0, 0, 0, 0)

        self.barLayout = QHBoxLayout()
        self.barLayout.addWidget(self.tableSelectCombo)
        self.barLayout.addWidget(self.updateTableButton)

        self.primaryLayout.addLayout(self.barLayout)
        self.primaryLayout.addWidget(self.dataWidget)

        self.fillTables()

    def fillTables(self):
        if self.connection is not None:
            tables = list()
            self.tableSelectCombo.clear()
            self.dataWidget.clear()

            cursor = self.connection.execute("select name from sqlite_master where type = 'table'")
            r = cursor.fetchone()
            while r:
                table_name = r[0]
                self.tableSelectCombo.addItem(table_name)
                tables.append(table_name)
                r = cursor.fetchone()

            cursor.close()

            self.fillData()

    def fillData(self):
        if self.connection is not None:
            self.dataWidget.clear()

            table_name = self.tableSelectCombo.currentText()
            if table_name:
                cursor = self.connection.cursor()
                cursor.execute("select * from " + table_name)
                r = cursor.fetchone()
                if r:
                    self.dataWidget.setColumnCount(len(r.keys()))
                    columns_names = r.keys()
                    self.dataWidget.setHorizontalHeaderLabels(columns_names)

                    row_index = 0
                    while r:
                        self.dataWidget.setRowCount(row_index + 1)
                        column_index = 0
                        for column in columns_names:
                            item = QTableWidgetItem(str(r[column]))
                            self.dataWidget.setItem(row_index, column_index, item)
                            column_index += 1
                        row_index += 1
                        r = cursor.fetchone()
                else:
                    self.dataWidget.setColumnCount(0)
                    self.dataWidget.setRowCount(0)

                cursor.close()

    def changeTable(self, another_table_name):
        self.fillData()


class DatabaseDialog(QDialog):
    def __init__(self, db_connection, parent):
        QDialog.__init__(self, parent)

        self.databaseWidget = DatabaseWidget(db_connection, self)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.databaseWidget)
