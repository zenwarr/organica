from threading import RLock

class Lockable:
	def __init__(self):
		self.lock = RLock()


