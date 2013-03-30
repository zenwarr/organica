from organica.utils.settings import globalSettings


_is_registered = False


def doRegister():
    global _is_registered

    if not _is_registered:
        _settings_to_register = (
                         ('log_file_name', None, str),
                         ('default_error_policy', 'ask', str),
                         ('disabled_plugins', [], (list, tuple)),
                         ('pool_operations_limit', 10, int),
                         ('quick_search', True, bool)
                         )

        s = globalSettings()
        for key, default, required_type in _settings_to_register:
            s.register(key, default, required_type)
        _is_registered = True
