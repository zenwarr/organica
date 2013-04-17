import os
import sys


if __name__ == '__main__':
    build_module_filename = os.path.join(os.path.dirname(__file__), 'build.py')
    if os.path.exists(build_module_filename):
        import imp
        build_module = imp.load_source('builder', build_module_filename)
        builder = build_module.Builder(os.path.dirname(__file__))
        builder.build()

    import organica.utils.constants as constants
    from organica.gui.application import runApplication

    # this will not work with something like py2exe, so we will need to create
    # some workaround
    constants.app_dir = os.path.dirname(os.path.realpath(__file__))

    sys.exit(runApplication())
