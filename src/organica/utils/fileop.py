import os
import logging
import shutil
from PyQt4.QtCore import QFileInfo
from PyQt4.QtGui import QMessageBox
from organica.utils.helpers import removeLastSlash, tr
from organica.utils.operations import globalOperationContext


_CancelCode = 'cancel'
_SkipCode = 'skip'


def copyFile(source_path, dest_path, remove_source=False, predicate=None, progress_weight=0, remove_root_dir=True):
    source_path = os.path.normcase(os.path.normpath(source_path))
    dest_path = os.path.normcase(os.path.normpath(dest_path))

    source_basename = os.path.basename(removeLastSlash(source_path))
    operation_title = tr('moving' if remove_source else 'copying')
    with globalOperationContext().newOperation('{0} {1}'.format(operation_title, source_basename), progress_weight):
        if not os.path.exists(source_path):
            raise IOError(tr('source path {0} does not exist').format(source_path))

        if not os.path.exists(os.path.dirname(dest_path)):
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        if isSameFile(source_path, dest_path):
            return

        # if source is link, do not copy, but create new link instead of destination
        if os.path.islink(source_path):
            link_target = os.readlink(source_path)
            # resolve relative links depending on directory
            if not os.path.isabs(link_target):
                link_target = os.path.join(os.path.dirname(source_path), link_target)
            os.symlink(link_target, dest_path)
            if remove_source:
                os.remove(source_path)
            return

        # count all files we should copy to provide correct progress values
        progress_increment = 100 / countFiles(source_path)
        if _do_copy(source_path, dest_path, remove_source, predicate, progress_increment, remove_root_dir=remove_root_dir,
                    first_level=True) == _CancelCode:
            globalOperationContext().currentOperation.cancel()


def _do_copy(source_path, dest_path, remove_source, predicate, progress_increment, remove_root_dir=True, first_level=False):
    op = globalOperationContext().currentOperation

    if predicate is not None and not predicate(source_path):
        return _SkipCode

    if os.path.isdir(source_path):
        if not os.path.exists(dest_path):
            try:
                os.mkdir(dest_path)
            except Exception as err:
                return _SkipCode if op.processError(tr('failed to create directory {0}: {1}').format(dest_path, err)) else _CancelCode
        else:
            if not os.path.isdir(dest_path):
                ans = _ask_resolve(tr('{0} is not directory. Delete it and create directory?').format(dest_path),
                                        QMessageBox.Yes|QMessageBox.No)
                if ans == QMessageBox.Cancel:
                    return _CancelCode
                elif ans != QMessageBox.Yes:
                    return _SkipCode

                try:
                    os.remove(dest_path)
                    os.mkdir(dest_path)
                except Exception as err:
                    return _SkipCode if op.processError(tr('failed to create directory {0}: {1}').format(dest_path, err)) else _CancelCode
            elif not first_level:
                ans = _ask_resolve(tr('directory {0} already exist{1}. Merge its contents with copied files?')
                                    .format(dest_path, ' and contains files' if os.listdir(dest_path) else ''),
                                   QMessageBox.Yes|QMessageBox.No)
                if ans == QMessageBox.Cancel:
                    return _CancelCode
                elif ans != QMessageBox.Yes:
                    return

        # iterate over all files in source and copy it
        skip_dir = first_level and not remove_root_dir
        for filename in os.listdir(source_path):
            src_filename = os.path.join(source_path, filename)
            ans = _do_copy(src_filename, os.path.join(dest_path, filename), remove_source, predicate, progress_increment)
            if ans == _CancelCode:
                return _CancelCode
            elif ans == _SkipCode:
                skip_dir = True

        # copy file meta-information from source
        try:
            shutil.copystat(source_path, dest_path)
            # and try to delete source directory
            if remove_source and not skip_dir:
                os.rmdir(source_path)
        except Exception as err:
            # but this is not critical error, so...
            op.addMessage(tr('fail while copying directory {0}: {1}').format(source_path, err), logging.WARNING)
    else:
        if os.path.exists(dest_path):
            ans = _ask_resolve(tr('file {0} already exists. Replace it with another file?').format(dest_path),
                               QMessageBox.Yes|QMessageBox.No)
            if ans != QMessageBox.Yes:
                return

        op.setProgressText(tr('Copying {0}').format(os.path.basename(removeLastSlash(source_path))))
        try:
            if remove_source:
                shutil.move(source_path, dest_path)
            else:
                shutil.copy2(source_path, dest_path)
        except Exception as err:
            errmsg = tr('failed to copy file {0} to {1}: {2}').format(source_path, dest_path, err)
            return _SkipCode if op.processError(errmsg) else _CancelCode
        op.setProgress(op.state.progress + progress_increment)


def _ask_resolve(text, buttons):
    def _ask(text, buttons):
        msgbox = QMessageBox(None)
        msgbox.setWindowTitle(tr('Copying files'))
        msgbox.setText(text)
        msgbox.setStandardButtons(buttons)
        return msgbox.exec_()
    return globalOperationContext().requestGuiCallback(lambda: _ask(text, buttons))[1]


def countFiles(path):
    if not os.path.exists(path):
        return 0
    elif not os.path.isdir(path):
        return 1
    else:
        return sum(countFiles(os.path.join(path, filename)) for filename in os.listdir(path))


def isSameFile(source_path, dest_path):
    return QFileInfo(source_path) == QFileInfo(dest_path)


def removeFile(path, predicate=None, progress_weight=0, remove_root_dir=True):
    if not os.path.exists(path):
        return

    with globalOperationContext().newOperation(tr('removing {0}').format(path), progress_weight):
        progress_increment = 100 / countFiles(path)
        _do_remove(path, predicate, progress_increment, True, remove_root_dir)


def _do_remove(path, predicate, progress_increment, first_level=False, remove_root_dir=True):
    if not os.path.exists(path):
        return

    op = globalOperationContext().currentOperation

    if predicate is not None and not predicate(path):
        return _SkipCode

    if not os.path.isdir(path):
        try:
            os.remove(path)
        except Exception as err:
            return _SkipCode if op.processError(tr('Failed to remove file: {0}').format(err)) else _CancelCode
    else:
        skip_dir = first_level and not remove_root_dir
        for filename in os.listdir(path):
            ans = _do_remove(os.path.join(path, filename), predicate, progress_increment, False, remove_root_dir)
            if ans == _CancelCode:
                return _CancelCode
            elif ans == _SkipCode:
                skip_dir = True

        if not skip_dir:
            os.rmdir(path)

    if op is not None:
        op.setProgress(op.state.progress + progress_increment)
