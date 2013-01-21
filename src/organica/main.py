import os
import locale

import organica.utils.constants as constants
from organica.application import globalApplication


def main():
    locale.setlocale(locale.LC_ALL, '')
    os.chdir(os.path.expanduser('~'))

    app = globalApplication()
    app.startUp()
    return_code = app.exec_()
    app.shutdown()
    return return_code
