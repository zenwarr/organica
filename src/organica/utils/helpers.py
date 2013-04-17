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
    return uncase(first) == uncase(second)


def uncase(text):
    return text.casefold() if hasattr(text, 'casefold') else text.lower()


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


def setWidgetTabOrder(widget, chain):
    if len(chain) >= 2:
        for widget_index in range(1, len(chain)):
            widget.setTabOrder(chain[widget_index - 1], chain[widget_index])


_q = (
    ('Tb', 1024 * 1024 * 1024 * 1024),
    ('Gb', 1024 * 1024 * 1024),
    ('Mb', 1024 * 1024),
    ('Kb', 1024)
)


def formatSize(size):
    for q in _q:
        if size >= q[1]:
            size = size / q[1]
            postfix = q[0]
            break
    else:
        postfix = 'b'
    return '{0} {1}'.format(round(size, 2), postfix)


def lastFileDialogPath():
    from organica.utils.settings import globalQuickSettings

    qs = globalQuickSettings()
    last_dir = qs['last_filedialog_path']
    return last_dir if isinstance(last_dir, str) else ''


def setLastFileDialogPath(new_path):
    from organica.utils.settings import globalQuickSettings

    qs = globalQuickSettings()
    if os.path.exists(new_path) and os.path.isfile(new_path):
        new_path = os.path.dirname(new_path)
    qs['last_filedialog_path'] = new_path


def first(iterable, default=None):
    try:
        return next(iter(iterable))
    except StopIteration:
        return default
