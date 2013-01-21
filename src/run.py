import sys
import os
import organica.main
import organica.utils.constants as constants


if __name__ == '__main__':
    constants.app_dir = os.path.dirname(__file__)
    sys.exit(organica.main.main())
