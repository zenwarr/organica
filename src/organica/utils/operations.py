import logging
from threading import Thread, Condition, current_thread
from queue import Queue
from copy import copy

from PyQt4.QtCore import Qt, QObject, pyqtSignal, QCoreApplication, QEvent, QTimer
from PyQt4.QtGui import QApplication

from organica.utils.lockable import Lockable
import organica.utils.constants as constants


class OperationError(Exception):
    pass


class OperationState:
    # values for OperationState.status
    NOT_STARTED = 0
    RUNNING = 1
    PAUSED = 2
    CANCELLED = 3
    COMPLETED = 4
    FAILED = 5

    _map_status = {
        NOT_STARTED: 'Not started',
        RUNNING: 'Running',
        PAUSED: 'Paused',
        CANCELLED: 'Cancelled',
        COMPLETED: 'Completed',
        FAILED: 'Failed'
    }

    def __init__(self):
        self.title = ''
        self.status = OperationState.NOT_STARTED
        self.progress = 0.0
        self.progressText = ''
        self.canPause = False
        self.canCancel = False
        self.messages = []  # each item is tuple - (text, level). Level is one of logging module
                            # level constants.
        self.results = {}
        self.errorCount = 0
        self.warningCount = 0

    @property
    def statusText(self):
        """Text representation of OperationState.status
        """

        return OperationState._map_status.get(self.status, 'Unknown')

    @property
    def isRunning(self):
        """Indicates that operation is running. In differense from status == OperationState.RUNNING this
        property is True when operation was started and not finished yet (status is OperationState.RUNNING
        or OperationState.PAUSED)
        """

        return self.status == OperationState.RUNNING or self.status == OperationState.PAUSED

    @property
    def isFinished(self):
        """Indicates that operation is finished. Returns true if status is OperationState.COMPLETED, OperationState.FAILED or
        OperationState.CANCELLED
        """

        return self.status in (OperationState.CANCELLED, OperationState.COMPLETED, OperationState.FAILED)


class _CallbackRequestEvent(QEvent):
    _eventType = QEvent.registerEventType()

    def __init__(self, operation, callback, *callbackArgs):
        super().__init__(self._eventType)
        self.__operation = operation
        self.__callback = callback
        self.__callbackArgs = callbackArgs

    def __call__(self):
        if self.__operation is not None and self.__callback is not None \
                                        and callable(self.__callback):
            result = self.__callable(*self.__callbackArgs)
            self.accept()
            self.__operation._reportCallbackProcessed(True, result)


class _GuiDispatcher(QObject):
    def customEvent(self, event):
        if isinstance(_CallbackRequestEvent, event):
            event()


_globalGuiDispatcher = None


def globalGuiDispatcher():
    global _globalGuiDispatcher
    if _globalGuiDispatcher is None:
        _globalGuiDispatcher = _GuiDispatcher()
    return _globalGuiDispatcher


class OperationContext(Lockable):
    """This class provides access to operation object in which context
    code is executed. It also helps writing operations without need to
    subclass Operation class.

    Using OperationContext class you can write functions supporting
    operation-specific features like indicating progress or controlling.
    Example of such code:

    with OperationContext().newOperation('special_operation') as context:
        with OperationContext().newOperation('subop', 10) as context2:
            context.addMessage('hello, world!')

    If this code executed when no other operation is active, first 'with' statement
    will create new _InlineOperation and start it. Second block will create and execute
    sub-operation in context of operation created by first block. Both operations are
    automatically finished.
    """

    def __init__(self):
        Lockable.__init__(self)
        self.__operations = {}

    @property
    def allOperations(self, thread=None):
        with self.lock:
            if thread is None:
                thread = current_thread()
            return self.__operations.get(thread.ident, [])

    @property
    def currentOperation(self):
        with self.lock:
            tid = current_thread().ident
            if tid in self.__operations:
                return self.__operations[tid][-1]
            else:
                return None

    @property
    def isInOperation(self):
        with self.lock:
            return self.currentOperation is not None

    def newOperation(self, title='', progress_weight=0, collect_results=False):
        with self.lock:
            inline_operation = _InlineOperation(title)
            if self.isInOperation:
                self.currentOperation.executeSubOperation(inline_operation, progress_weight, collect_results)
            else:
                inline_operation.run(Operation.RUNMODE_THIS_THREAD)
            return inline_operation

    def _enterOperation(self, operation):
        with self.lock:
            tid = current_thread().ident
            if tid in self.__operations:
                self.__operations[tid].append(operation)
            else:
                self.__operations[tid] = [operation]

    def _leaveOperation(self):
        with self.lock:
            tid = current_thread().ident
            if tid in self.__operations:
                if len(self.__operations[tid]) == 1:
                    del self.__operations[tid]
                else:
                    self.__operations[tid].pop()


_globalOperationContext = None


def globalOperationContext():
    global _globalOperationContext
    if _globalOperationContext is None:
        _globalOperationContext = OperationContext()
    return _globalOperationContext


class Operation(QObject, Lockable):
    ## signals
    stateChanged = pyqtSignal(OperationState)
    statusChanged = pyqtSignal(int)
    progressChanged = pyqtSignal(float)
    progressTextChanged = pyqtSignal(str)
    canPauseChanged = pyqtSignal(bool)
    canCancelChanged = pyqtSignal(bool)
    messageAdded = pyqtSignal(str, int)
    errorCountIncreased = pyqtSignal(int)
    warningCountIncreased = pyqtSignal(int)
    newResult = pyqtSignal(str, object)
    finished = pyqtSignal(int)

    # predefined commands for use with sendCommand
    PAUSE_COMMAND = 'pause'
    RESUME_COMMAND = 'resume'
    CANCEL_COMMAND = 'cancel'

    # values for runMode
    RUNMODE_NOT_STARTED = 0
    RUNMODE_THIS_THREAD = 1
    RUNMODE_NEW_THREAD = 2

    def __init__(self, title=''):
        QObject.__init__(self)
        Lockable.__init__(self)

        self.__state = OperationState()
        self._commandsQueue = Queue()
        self.__waitFinish = Condition(self.lock)
        self.__waitResults = Condition(self.lock)
        self._manualScope = False  # if True, operation will not be automatically finished
                                   # Ignored if operation run in new thread.

        self.__runMode = self.RUNMODE_NOT_STARTED
        self.__requestDoWork = True
        self.__state.title = title
        self.__waitUserCallback = Condition(self.lock)
        self.__subOperationStack = []

    @property
    def title(self):
        with self.lock:
            return self.__state.title

    @property
    def state(self):
        with self.lock:
            return self.__state

    @property
    def runMode(self):
        with self.lock:
            return self.__runMode

    @property
    def requestDoWork(self):
        with self.lock:
            return self.__requestDoWork

    @requestDoWork.setter
    def requestDoWork(self, value):
        with self.lock:
            self.__requestDoWork = value

    def sendCommand(self, command):
        """Send command to operation code. Operation can process commands in two ways:
        1. Reimplement onCommandReceived method which is called each time new command sent.
        This method should return True if processes command.
        2. Use takeCommand method.
        """

        with self.lock:
            if command is None:
                raise OperationError('invalid command')
            if self.state.isFinished:
                raise OperationError('operation already finished')
            if not self.onCommandReceived(command):
                self._commandsQueue.put(command)

    def run(self, runMode=RUNMODE_NEW_THREAD):
        """Start operation. Failed if operation already started.
        """

        with self.lock:
            if self.__state.status != OperationState.NOT_STARTED:
                raise OperationError('operation already started')
            if runMode not in (self.RUNMODE_THIS_THREAD, self.RUNMODE_NEW_THREAD):
                raise OperationError('invalid run mode')
            self.__runMode = runMode

        if runMode == self.RUNMODE_THIS_THREAD:
            self.__work()
        elif runMode == self.RUNMODE_NEW_THREAD:
            Thread(target=self.__work).start()

    def sendPause(self):
        """Send pause command to operation
        """

        self.sendCommand(self.PAUSE_COMMAND)

    def sendResume(self):
        """Send resume command to operation. Note that this method does not check if resume
        command has any meaning at the moment.
        """

        self.sendCommand(self.RESUME_COMMAND)

    def sendCancel(self):
        """Send cancel command to operation. Note thet this method does not check if cancel
        command has any meaning at the moment.
        """

        self.sendCommand(self.CANCEL_COMMAND)

    def togglePauseResume(self):
        """If operation state is OperationState.PAUSED, send resume command, if state is OperationState.RUNNING,
        send pause command. Otherwise do nothing
        """

        with self.lock:
            if self.state.status == OperationState.RUNNING:
                self.sendPause()
            elif self.state.status == OperationState.PAUSED:
                self.sendResume()

    def waitForFinish(self):
        """Block current thread until operation finished. Return operation final status.
        """

        with self.__waitFinish:
            if not self.state.isFinished:
                self.__waitFinish.wait()
            return self.state.status

    def waitForResult(self):
        """Block current thread until operation adds new result to results list or
        operation finishes.
        """

        with self.__waitResults:
            if not self.state.isFinished:
                self.__waitResults.wait()

    def takeCommand(self, block=True, timeout=None):
        """Get oldest command from queue, removing it. Arguments :block: and :timeout: has
        same meaning as Queue.get arguments with same name.
        """

        with self.lock:
            return self._commandsQueue.get(block, timeout)

    def finish(self):
        """Finish operation. If operation has error messages (state.errorCount > 0) final
        state will be OperationState.FAILED, otherwise it will be set to OperationState.COMPLETED.
        """

        with self.lock:
            if self.state.isFinished:
                raise OperationError('operation already finished')
            self.setProgress(100)
            self.setStatus(OperationState.FAILED if self.state.errorCount > 0 else OperationState.COMPLETED)
            globalOperationContext()._leaveOperation()

    def cancel(self):
        """Cancel operation. Final state will be set to OperationState.CANCELLED
        """

        with self.lock:
            if self.state.isFinished:
                raise OperationError('operation already finished')
            self.setStatus(OperationState.CANCELLED)

    def doWork(self):
        """This method should be reimplemented to contain operation code.
        """

        raise NotImplementedError()

    def onCommandReceived(self, command):
        """Method called before received command will be placed into queue.
        If method returns true, command will be considered as executed and will
        not be placed into queue.
        This method is always executed in context of thread that sends command.
        """

        return False

    def __work(self):
        """Private method to execute operation code. Operation code contained in reimplemented
        Operation.doWork method will be at least one time. Another subsequent calls will be made
        if requestDoWork is True (this flag reset before calling doWork).
        Any exception raised in doWork is catched but will not be passed to outer methods but
        message logged (with Operation.addMessage). Exception raised does not make operation to
        be finished. After each call to doWork QApplication.processEvents is called to prevent
        application GUI from freezing.
        """

        with self.lock:
            if self.state.status != OperationState.NOT_STARTED:
                raise OperationError('operation already had been started')
            self.__start()
            self.__requestDoWork = True
            while not self.state.isFinished:
                if self.__requestDoWork:
                    self.__requestDoWork = False
                    try:
                        self.doWork()
                    except Exception as exc:
                        self.addMessage(exc, logging.ERROR)
                    except:
                        self.addMessage('undefined error while executing operation', logging.ERROR)
                    QApplication.processEvents()
                elif not self._manualScope or self.runMode == Operation.RUNMODE_NEW_THREAD:
                    self.finish()
                else:
                    break

    def __setStateAttribute(self, attrib_name, value):
        with self.lock:
            if self.state.isFinished:
                raise OperationError('operation already finished')

            if getattr(self.state, attrib_name) != value:
                setattr(self.state, attrib_name, value)
                self.stateChanged.emit(self.state)
                attrib_signal = attrib_name + 'Changed'
                getattr(self, attrib_signal).emit(value)

    def setStatus(self, new_status):
        with self.lock:
            if self.state.status != new_status:
                self.__setStateAttribute('status', new_status)

                if self.state.isFinished:
                    self.__waitFinish.notify_all()
                    self.__waitResults.notify_all()

                    try:
                        self.__callbackAccepted = False
                        self.__waitUserCallback.notify_all()
                    except RuntimeError:
                        pass

                    self.finished.emit(self.state.status)

    def setProgress(self, new_progress):
        if new_progress < 0 or new_progress > 100:
            raise TypeError('invalid argument :new_progress: - should be in range 0...100')
        self.__setStateAttribute('progress', new_progress)

    def setProgressText(self, new_progress_text):
        self.__setStateAttribute('progressText', new_progress_text)

    def setCanPause(self, new_can_pause):
        self.__setStateAttribute('canPause', new_can_pause)

    def setCanCancel(self, new_can_cancel):
        self.__setStateAttribute('canCancel', new_can_cancel)

    def addResult(self, new_result_name, new_result_value):
        with self.lock:
            if self.state.isFinished:
                raise OperationError('operation already finished')

            self.state.results[new_result_name] = new_result_value
            self.__waitResults.notify_all()
            self.stateChanged.emit(self.state)
            self.newResult.emit(new_result_name, new_result_value)

    def addMessage(self, message, level):
        """Add message to operation message list. :level: should be from logging module
        level enumeration.
        """

        with self.lock:
            if self.state.isFinished:
                raise OperationError('operation already finished')

            self.state.messages.append((message, level))
            if level >= logging.ERROR:
                self.state.errorCount += 1
            elif level == logging.WARNING:
                self.state.warningCount += 1

            self.stateChanged.emit(self.state)
            if level >= logging.ERROR:
                self.errorCountIncreased.emit(self.state.errorCount)
            elif level == logging.WARNING:
                self.warningCountIncreased.emit(self.state.warningCount)

    def executeSubOperation(self, subop, progress_weight=0.0, process_results=False,
                            result_name_converter=None, finish_on_fail=False):
        """Operation can execute sub-operation in its context. Operation that executes sub-operation
        is called parent of it. No new thread will be created for sub-operation.
        So this method will return control after sub-operation doWork cycle is over. If sub-operation
        uses manual scope, it can still be not finished.
        When sub-operation will be finished, progress of parent operation increases on progress_weight
        percents. During executing of sub-operation parent progress will change from its value at moment
        of calling this method to this value + progress_weight.
        Changing sub-operation progress text will cause parent operation progress text to be changed to
        sub-operation progress text. Parent progress text will be restored after child finish.
        Before executing sub-operation parent operation canPause and canCancel flags will be set to sub-operation
        corresponding values and restored after finishing.
        Messages logged by sub-operation will be logged to parent-operation also.

        If :process_results: is True, results generated by sub-operation will be added to parent operation too.
        If :finish_on_fail: is True, parent operation will be finished if sub-operation fails.

        This method should be used by operation code, not by code outside. Method should be called
        only from thread in which operation executes.
        """

        with self.lock:
            if self.state.isFinished:
                raise OperationError('cannot execute sub-operation in context of finished operation')
            if self.state.status != OperationState.RUNNING:
                raise OperationError('operation state should be RUNNING to execute sub-operation')
            if subop is None or subop.state.status != OperationState.NOT_STARTED:
                raise OperationError('invalid sub-operation: should be alive and not started')

            # normalize progress_weight value to be in range 0...100
            if progress_weight < 0.0:
                progress_weight = 0.0
            elif progress_weight > 100.0:
                progress_weight = 100.0

            self.__subOperationStack.append((subop, copy(self.state), progress_weight, process_results,
                                            result_name_converter, finish_on_fail))
            saved_state = self.state

            self.setCanPause(subop.state.canPause)
            self.setCanCancel(self.state.canCancel and subop.canCancel)
            self.setProgressText(subop.state.progressText or self.state.progressText)

            # if current progress value + progress_weight is greater 100, decrease
            # current progress
            if self.state.progress + progress_weight > 100.0:
                self.setProgress(100.0 - progress_weight)

            # connect signals to make it possible to react on sub-op changes
            subop.progressChanged.connect(self.__onSubopProgress, Qt.DirectConnection)
            subop.progressTextChanged.connect(self.__onSubopProgressText, Qt.DirectConnection)
            subop.messageAdded.connect(self.addMessage, Qt.DirectConnection)
            subop.canPauseChanged.connect(self.setCanPause, Qt.DirectConnection)
            subop.canCancelChanged.connect(lambda canCancel: self.setCanCancel(saved_state.canCancel and canCancel),
                                           Qt.DirectConnection)
            subop.statusChanged.connect(self.__onSubopStatus, Qt.DirectConnection)

            if process_results:
                if result_name_converter is not None:
                    subop.newResult.connect(lambda k, v: self.addResult(result_name_converter(k), v),
                                            Qt.DirectConnection)
                else:
                    subop.newResult.connect(self.addResult, Qt.DirectConnection)

            subop.finished.connect(self.__onSubopFinish)

            subop.run(self.RUNMODE_THIS_THREAD)

    def __onSubopProgress(self, np):
        with self.lock:
            self.setProgress(self.__subOperationStack[-1][1].progress +
                         np * (self.__subOperationStack[-1][2] / 100))

    def __onSubopProgressText(self, subop_progress_text):
        with self.lock:
            saved_state = self.__subOperationStack[-1][1]
            self.setProgressText(subop_progress_text or saved_state.progressText)

    def __onSubopStatus(self, status):
        with self.lock:
            if status == OperationState.RUNNING or status == OperationState.PAUSED:
                self.setStatus(status)

    def __onSubopFinish(self):
        with self.lock:
            sd = self.__subOperationStack.pop()

            subop = sd[0]
            saved_state = sd[1]
            subop_progress_weight = sd[2]
            finish_on_fail = sd[5]

            # restore some state values
            self.setCanPause(saved_state.canPause)
            self.setCanCancel(saved_state.canPause)
            self.setProgress(saved_state.progress + subop_progress_weight)
            self.setProgressText(saved_state.progressText)

            # sd[5] -> finish_on_fail
            if finish_on_fail and subop.state.status == OperationState.FAILED:
                self.finish()  # final state will be set to OperationState.FAILED as error messages
                                 # are directly written to operation

    def __start(self):
        with self.lock:
            self.setStatus(OperationState.RUNNING)
            globalOperationContext()._enterOperation(self)

    def requestGuiCallback(self, callback, **callback_args):
        """This method allows operation to request executing a piece of code in
        context of user (gui) thread. Method blocks current thread until
        given callback returns or is rejected. Returns tuple (accepted, result).
        """

        # check if we are in gui thread already. In this case just invoke callback
        if current_thread() == constants.gui_thread:
            return (True, callback(**callback_args))
        else:
            with self.lock:
                self.__callbackAccepted, self.__callbackResult = False, None
                request_event = _CallbackRequestEvent(self, callback, **callback_args)
                QCoreApplication.postEvent(globalGuiDispatcher(), request_event)
                self.__waitUserCallback.wait()
                return (self.__callbackAccepted, self.__callbackResult)

    def _reportCallbackProcessed(self, accepted, result=None):
        with self.lock:
            self.__callbackAccepted, self.__callbackResult = accepted, result
            self.__waitUserCallback.notify_all()


class WrapperOperation(Operation):
    """Operation allows executing any callable as operation. Callable result
    is accessible in results dict under 'result' name.
    """

    RESULT_NAME = 'result'

    def __init__(self, functor=None, title=''):
        super().__init__(title)
        self.__functor = functor

    def doWork(self):
        try:
            if self.__functor is not None:
                self.addResult(self.RESULT_NAME, self.__functor())
        finally:
            self.finish()


class DelayOperation(Operation):
    """Operation that executes at least given given number
    of milliseconds and does nothing.
    """

    def __init__(self, delay):
        super().__init__('delay for {0} seconds'.format(delay))
        self.__delay = delay

    def doWork(self):
        QTimer.singleShot(self.__delay, self.finish)


class _InlineOperation(Operation):
    """This is helper class which allows executing of operations
    that are not implemented as a derived class. It supports context manager
    protocol.
    """

    def __init__(self, title):
        super().__init__(title)
        self._manualScope = True

    def doWork(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, t, v, tp):
        if t is not None:
            self.addMessage('exception: {0}'.format(t), logging.ERROR)
        self.finish()
