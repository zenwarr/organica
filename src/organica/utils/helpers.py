from PyQt4.QtCore import QCoreApplication


def each(iterable, pred):
    if pred is None or not callable(pred):
        raise TypeError('invalid predicate')
    for i in iterable:
        if not pred(i):
            return False
    else:
        return True


def escape(text, need_escape):
    escaped = ''
    escaping = False
    for c in text:
        escaped = escaped + ('\\{0}'.format(c) if c in need_escape and not escaping else c)
        escaping = not escaping and c == '\\'
    return escaped


def tr(text, context='', disambiguation=None):
    return QCoreApplication.translate(context, text, disambiguation, QCoreApplication.UnicodeUTF8)


def cicompare(first, second):
    # use str.casefold if available
    if hasattr(first, 'casefold'):
        return first.casefold() == second.casefold()
    else:
        return first.lower() == second.lower()
