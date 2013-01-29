import os


if __name__ == '__main__':
    build_module_filename = os.path.join(os.path.dirname(__file__), 'build.py')
    if os.path.exists(build_module_filename):
        import imp
        build_module = imp.load_source('builder', build_module_filename)
        build_module.build_project()

    import organica.utils.constants as constants
    from organica.gui.application import runApplication

    constants.app_dir = os.path.dirname(__file__)
    runApplication()
