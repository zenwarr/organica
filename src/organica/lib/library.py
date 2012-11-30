import os, sys, sqlite3, logging
from organica.utils.lockable import Lockable
import organica.utils.helpers as helpers
from organica.lib.filters import QueryString
from organica.lib.objects import Object, Tag, TagClass
from PyQt4.QtCore import QObject, pyqtSignal

logger = logging.getLogger(__name__)

class LibraryError(Exception):
	def __init__(self, desc):
		super().__init__(desc)

class Library(QObject, Lockable):
	class TransactionCursor:
		def __init__(self, lib):
			super().__init__()
			self.lib = lib
			self.enter_count = 0

		def __enter__(self):
			if self.enter_count == 0:
				self.cursor = self.lib.connection.cursor()
			self.enter_count += 1
			return self.cursor

		def __exit__(self, t, v, tp):
			self.enter_count -= 1
			if self.enter_count == 0:
				if t is None:
					self.lib.connection.commit()
				else:
					self.lib.connection.rollback()
				self.cursor.close()

	class CursorKeeper:
		def __init__(self, cursor):
			self.cursor = cursor

		def __enter__(self):
			return self.cursor

		def __exit__(self):
			self.cursor.close()

	metaChanged = pyqtSignal(object)
	tagClassCreated = pyqtSignal(TagClass)

	def __init__(self):
		QObject.__init__(self)
		Lockable.__init__(self)
		self.__conn = None
		self.__filename = ''
		self.__meta = {}

	@staticmethod
	def loadLibrary(filename):
		if not os.path.exists(filename):
			raise LibraryError('database file {0} does not exists'.format(filename))
		lib = Library()
		lib.__connect(filename)
		with self.transactionCursor() as c:
			c.execute("select 1 from organica_meta where name = 'organica' "\
			          + "and value = 'is magic'")
			if not c.fetchone():
				raise LibraryError('database {0} is not organica database'.format(filename))
		lib.__loadMeta()
		lib.__loadTagClasses()
		return lib

	@staticmethod
	def createLibrary(filename):
		if os.path.exists(filename):
			raise LibraryError('database file already exists')
		lib = Library()
		lib.__connect(filename)
		with lib.transactionCursor() as c:
			c.executescript("""
			       	pragma encoding = 'UTF-8';

			       	create table organica_meta(name text collate nocase,
			       	                           value text);

					create table objects(id integer primary key autoincrement,
					                     display_name text collate nocase,
					                     obj_flags integer);

					create table tag_classes(id integer primary key,
					                         name text collate nocase unique,
					                         value_type integer,
					                         hidden integer);

					create table links(object_id integer,
					                   tag_class_id integer,
					                   tag_id integer,
					                   foreign key(object_id) references objects(id),
					                   unique(object_id, tag_type, tag_id));
			                """)
			self.addMeta('organica', 'is magic')
		return lib

	@staticmethod
	def isCorrectIdentifier(name):
		return helpers.each(name, lambda c: c.isalnum() or c in '_$')

	def getMeta(self, meta_name, default = ''):
		return self.__meta[meta_name] if meta_name in self.__meta else default

	def testMeta(self, meta_name):
		return meta_name in self.__meta

	def setMeta(self, meta_name, meta_value):
		with self.lock:
			if not self.isCorrectIdentifier(meta_name):
				raise LibraryError('invalid meta name {0}'.format(meta_name))
			with self.transactionCursor() as c:
				if meta_name in self.__meta:
					if meta_value == self.__meta[meta_name]:
						return
					c.execute('update organica_meta set value = ? where name = ?',
							  (meta_value, meta_name))
				else:
					c.execute('insert into organica_meta(name, value) values(?, ?)',
					          (meta_name, meta_value))
				self.__meta[meta_name] = meta_value
				self.metaChanged.emit(self.__meta)

	def removeMeta(self, meta_name):
		with self.lock:
			with self.transactionCursor() as c:
				if isinstance(meta_name, QueryString):
					c.execute('delete from organica_meta where ' + meta_name.generateSqlComparision())
					self.__loadMeta()
				else:
					c.execute('delete from organica_meta where name = ?', (meta_name, ))
					del self.__meta[meta_name]
				self.metaChanged.emit(self.__meta)

	@property
	def allMeta(self):
		with self.lock:
			return self.__meta

	def __loadMeta(self):
		with self.lock:
			self.__meta.clear()
			with self.cursor() as c:
				c.execute("select name, value from organica_meta")
				for r in c.fetchall():
					if not self.isCorrectIdentifier(r[0]):
						logger.warning('invalid meta name "{0}", ignored'.format(r[0]))
					else:
						self.meta[r[0]] = r[1]

	def __loadTagClasses(self):
		with self.lock:
			with self.transactionCursor() as c:
				c.execute("select id, name, ctype, hidden from tag_classes")
				for r in c.fetchall():
					if not self.isCorrectIdentifier(r[1]):
						logger.warn('invalid tag class name: "{0}", ignored'.format(r[1]))
						continue
					tc = TagClass(self, r[0])
					tc.name = r[1]
					tc.valueType = r[2]
					tc.hidden = r[3]
					self.__tagClasses[tc.name] = tc

	def createTagClass(self, name, value_type, is_hidden = False):
		with self.lock:
			if not self.isCorrectIdentifier(name):
				raise ArgumentError('invalid tag class name: {0}'.format(name))
			if self.tagClass(name):
				raise LibraryError('tag class with name {0} already exists'.format(name))

			tc = TagClass(self, c.lastrowid)
			tc.name, tc.valueType, tc.hidden = name, value_type, is_hidden
			table_schema = self.schemaForTagClass(tc)
			with self.transactionCursor() as c:
				c.execute('insert into tag_classes(name, value_type, hidden) ' \
				          + 'values(?, ?, ?)', (name, value_type, hidden))
				c.execute(table_schema)

			self.tagClasses[name] = tc
			emit self.tagClassCreated(tc)

	def schemaForTagClass(self, tc):
		known_types = {
			TagValue.TYPE_TEXT: 'value text',
			TagValue.TYPE_NUMBER: 'value integer',
			TagValue.TYPE_LOCATOR: 'scheme text, value text',
			TagValue.TYPE_OBJECT_REFERENCE: 'value integer, foreign key(id) references objects(id)'
		}
		if tc.tagValue not in known_types:
			raise ArgumentError('unknown value type for tag class')
		return 'create table {0}({1})'.format(self.tableNameForTagClass(tc),
		                                      known_types[tc.tagValue])

	def tableNameForTagClass(self, tc):
		if isinstance(TagClass, tc):
			tc = tc.name
		return '__{0}_tags'.format(tc)

	@property
	def connection(self):
		with self.lock:
			return self.__conn

	def disconnect(self):
		with self.lock:
			if self.__conn is not None:
				self.__conn.close()

	@property
	def databaseFilename(self):
		with self.lock:
			return self.__filename

	def transactionCursor(self):
		if hasattr(self, 'transactionCursor'):
			return self.transactionCursor if self.transactionCursor else self.TransactionCursor(self)
		else:
			return self.TransactionCursor(self)

	def cursor(self):
		return self.CursorKeeper(self.connection.cursor())

	def __connect(self, filename):
		self.__conn = sqlite3.connect(filename)
		with self.transactionCursor() as c:
			c.execute('pragma foreign_keys = on')
