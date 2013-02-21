import json
import os

from PyQt4.QtCore import QCoreApplication


def each(iterable, pred):
    if pred is None or not callable(pred):
        raise TypeError('invalid predicate')
    for i in iterable:
        if not pred(i):
            return False
    else:
        return True


def escape(text, chars_to_escape):
    escaped = ''
    escaping = False
    for c in text:
        escaped += ('\\{0}'.format(c) if c in chars_to_escape and not escaping else c)
        escaping = not escaping and c == '\\'
    return escaped


def tr(text, context='', disambiguation=None):
    return QCoreApplication.translate(context, text, disambiguation, QCoreApplication.UnicodeUTF8)


def cicompare(first, second):
    # use str.casefold if available
    if hasattr(first, 'casefold') and hasattr(second, 'casefold'):
        return first.casefold() == second.casefold()
    else:
        return first.lower() == second.lower()


def readJsonFile(source):
    if hasattr(source, 'fileno'):
        # check if file has zero size and return None in this case
        source_size = os.fstat(source.fileno()).st_size
        if source_size == 0:
            return None

    return json.load(source)


def removeLastSlash(filename):
    if not isinstance(filename, str) or not (filename.endswith('\\') or filename.endswith('/')):
        return filename
    else:
        return filename[:-1]
