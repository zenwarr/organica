from organica.utils.extend import globalObjectPool


class ProfileManager(object):
    @staticmethod
    def genericProfile():
        from organica.generic.profile import GENERIC_PROFILE_UUID
        return ProfileManager.getProfile(GENERIC_PROFILE_UUID)

    @staticmethod
    def getProfile(profile_uuid):
        r = globalObjectPool().objects(group='profile', predicate=(lambda obj: obj.uuid == profile_uuid))
        return r[0] if r else None

    @staticmethod
    def allProfiles():
        return globalObjectPool().objects(group='profile')
