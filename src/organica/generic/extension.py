from organica.utils.extend import globalObjectPool


GENERIC_EXTENSION_UUID = '23bdf9f9-b025-4516-bde7-dd512eae738a'


def register():
    pool = globalObjectPool()

    from organica.generic.profile import GenericProfile
    pool.add(GenericProfile())

    from organica.generic.nodeeditor import GenericNodeEditorProvider
    pool.add(GenericNodeEditorProvider())
