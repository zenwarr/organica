from organica.utils.settings import globalSettings


_is_registered = False


def doRegister():
    global _is_registered

    if not _is_registered:
        _settings_to_register = (
                         ('log_file_name', None),
                         ('default_error_policy', 'ask')
                         )

        s = globalSettings()
        for key, default in _settings_to_register:
            s.register(key, default)
        _is_registered = True
