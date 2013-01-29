from organica.utils.settings import globalSettings


_settings_to_register = (
                         ('log_file_name', None),
                         )
_is_registered = False


def doRegister():
    global _is_registered
    global _settings_to_register

    if not _is_registered:
        s = globalSettings()
        for key, default in _settings_to_register:
            s.register(key, default)
        _is_registered = True
