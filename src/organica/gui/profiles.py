from organica.utils.extend import globalObjectPool


def genericProfile():
    from organica.generic.profile import GenericProfileUuid
    return getProfile(GenericProfileUuid)

def getProfile(profile_uuid):
    r = globalObjectPool().objects(group='profile', predicate=(lambda obj: obj.uuid == profile_uuid))
    return r[0] if r else None

def allProfiles():
    return globalObjectPool().objects(group='profile')
