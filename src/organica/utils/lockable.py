from threading import RLock


class Lockable(object):
    def __init__(self):
        self.lock = RLock()
