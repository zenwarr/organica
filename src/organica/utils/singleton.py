"""
Base class for singleton objects
"""

class Singleton:
    __singleton_inited = False

    def __init__(self):
        if not self.__singleton_inited:
            self.__singleton_inited = True
            self.singleton_init()

    def __new__(cls):
        if not hasattr(cls, 'instance'):
            cls.instance = super(Singleton, cls).__new__(cls)
        return cls.instance

    def singleton_init(self):
        pass
