class ObjectProxyError(Exception):
	def __init__(self):
		super().__init__('no target for object proxy')

class ObjectProxy:
	"""
	Helper class to easy creation of proxy objects
	"""
	__target = None

	@property
	def target(self):
		return self.__target

	@target.setter
	def setTarget(self, value):
		self.__target = value

	def __check(self):
		if not self.__target:
			raise ObjectProxyError()

	def __getattr__(self, name):
		self.__check()
		return getattr(self.target, name)

	def __setattr__(self, name, value):
		self.__check()
		setattr(self.target, name, value)

	def __delattr__(self, name):
		self.__check()
		delattr(self.target, name)

def each(iterable, pred):
	if pred is None or not callable(pred):
		raise TypeError('invalid predicate')
	for i in iterable:
		if not pred(i):
			return False
	else:
		return True

def __escape(text, need_escape):
    escaped = ''
    escaping = False
    for c in text:
        escaped.append('\\{0}'.format(c) if c in need_escape and not escaping else c)
        escaping = not escaping and c == '\\'
    return escaped


