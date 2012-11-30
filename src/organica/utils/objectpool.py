from organica.utils.lockable import Lockable
from PyQt4.QtCore import QObject, pyqtSignal

class ObjectPool(QObject, Lockable):
	newObject = pyqtSignal(object, str)
	objectRemoved = pyqtSignal(object, str)

	def __init__(self):
		self.__allGroups = {}

	@property
	def allGroups(self):
		with self.lock:
			return self.__allGroups

	def addObject(self, object, group):
		if group is None or len(group) == 0:
			raise ArgumentError('invalid group name')

		with self.lock:
			if object not in self.__allGroups[group]:
				self.__allGroups[group].append(object)
				self.newObject.emit(group, object)

	def removeObject(self, object, group = None):
		with self.lock:
			if group is None:
				for g in self.__allGroups.keys():
					if object in self.__allGroups[g]:
						self.__allGroups[g].remove(object)
						self.objectRemoved.emit(object, g)
			elif group in self.__allGroups.keys():
				if object in self.__allGroups[group]:
					self.__allGroups[group].remove(object)
					self.objectRemoved.emit(object, group)

	def removeExtensionObjects(self, ext_uuid):
		with self.lock:
			for g in self.__allGroups.keys():
				for obj in self.__allGroups[g]:
					if obj.extensionUuid == ext_uuid:
						self.__allGroups[g].remove(obj)

	def objects(self, group, pred = None):
		if pred in not None and not callable(pred):
			raise TypeError('callable expected')
		if group is None or len(group) == 0:
			raise ArgumentError('invalid group name')

		return [x for x in self.__allGroups[group] if pred is None or \
				pred(x) == True]

	def object(self, group, pred = None):
		obj_list = self.objects(group, pred)
		return None if len(obj_list) < 0 else obj_list[0]
