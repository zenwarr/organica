import logging
from threading import Lock, RLock, Thread, Condition, current_thread
from organica.utils.singleton import Singleton
from organica.utils.lockable import Lockable
from PyQt4 import QtCore
from PyQt4.QtCore import (QObject, pyqtSignal, QCoreApplication, QObject, QEvent,
                          QTimer)
from PyQt4.QtGui import QApplication

class OperationError(Exception):
    def __init__(self, desc = ''):
        super().__init__(desc)

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

class OperationState:
    def __init__(self):
        self.title = ''
        self.status = NOT_STARTED
        self.progress = 0.0
        self.progressText = ''
        self.canPause = False
        self.canCancel = False
        self.messages = []
        self.results = {}
        self.errorCount = 0
        self.warningCount = 0

    @property
    def statusText(self):
        """
        Text representation of OperationState.status
        """
        return _map_status[self.status] if self.status in _map_status else 'Unknown'

    @property
    def isRunning(self):
        """
        Indicates that operation is running. In differense from status == RUNNING this
        property is True when operation was started and not finished yet (status is RUNNING
        or PAUSED)
        """
        return self.status == RUNNING or self.status == PAUSED

    @property
    def isFinished(self):
        """
        Indicates that operation is finished. Returns true if status is COMPLETED, FAILED or
        CANCELLED
        """
        return self.status in (CANCELLED, COMPLETED, FAILED)

class _CallbackRequestEvent(QEvent):
    __eventType = QEvent.registerEventType()

    def __init__(self, operation, callback, *callbackArgs):
        super().__init__(self.__eventType)
        self.__operation = operation
        self.__callback = callback
        self.__callbackArgs = callbackArgs

    def __call__(self):
        if self.__operation is not None and self.__callback is not None \
           and callable(self.__callback):
            result = self.__callable(*self.__callbackArgs)
            self.accept()
            self.__operation.reportCallbackProcessed(True, result)

class _GuiDispatcher(QObject, Singleton):
    def customEvent(self, event):
        if isinstance(_CallbackRequestEvent, event):
            event()

class OperationContext(Singleton, Lockable):
    """
    This class provides access to operation object in which context
    code is executed. It also helps writing operations without need to
    subclass Operation class.

    Using OperationContext class you can write functions supporting
    operation-specific features like indicating progress or controlling.
    Example of such code:

    with OperationContext().newOperation('special_operation') as context:
    	with OperationContext().newOperation('subop', 10) as context2:
    		context.addMessage('hello, world!')

    If this code executed when no other operation is active, first 'with' statement
    will create new InlineOperation and start it. Second block will create and execute
    sub-operation in context of operation created by first block. Both operations are
    automatically finished.
    """

    @property
    def currentOperation(self):
        with self.lock:
            return self.__currentOperation

    @property
    def isInOperation(self):
        with self.lock:
            return self.__currentOperation is not None

    def __getattr__(self, name):
        with self.lock:
            if self.__currentOperation is None:
                raise OperationError('calling OperationContext method when no operation is active')
            return getattr(self.__currentOperation, name)

    def __setattr__(self, name, value):
        with self.lock:
            if self.__currentOperation is None:
                raise OperationError('calling OperationContext method when no operation is active')
            return setattr(self.__currentOperation, name, value)

    def __enter__(self):
        return self

    def __exit__(self, t, v, tb):
        with self.lock:
            if self.isInOperation:
                if t is not None:
                    self.addMessage('exception: {0}'.format(t), logging.ERROR)
                self.complete()
            return False

    def newOperation(self, title = '', prog_weigth = 0, collect_results = False):
        with self.lock:
            if self.isInOperation:
                self.executeSubOperation(InlineOperation(title), prog_weigth, collect_results)
            else:
                InlineOperation(title).run(Operation.RUNMODE_THIS_THREAD)

    # private interface for Operation class

    def enterOperation(self, operation):
        with self.lock:
            cthread = threading.current_thread()
            if cthread in self.__threads:
                self.__threads[cthread].append(operation)
            else:
                self.__threads[cthread] = [operation]

    def leaveOperation(self):
        with self.lock:
            cthread = threading.current_thread()
            if cthread in self.__threads:
                self.__threads.remove(cthread)

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
    PAUSE_COMMAND = 'PAUSE'
    RESUME_COMMAND = 'RESUME'
    CANCEL_COMMAND = 'CANCEL'

    # values for runMode
    RUNMODE_NOT_STARTED = 0
    RUNMODE_THIS_THREAD = 1
    RUNMODE_NEW_THREAD = 2

    def __init__(self, title = ''):
        super().__init__()
        self.__state = OperationState()
        self.__commandsStack = []
        self.__commandsLock = Lock()
        self.__waitCommand = Condition(self.__commandsLock)
        self.__waitFinish = Condition(self.lock)
        self.__waitResults = Condition(self.lock)

        self.__runMode = self.RUNMODE_NOT_STARTED
        self.__requestDoWork = True
        self.__state.title = title
        self.__userCallbackLock = Lock()
        self.__waitUserCallback = Condition(self.__userCallbackLock)

    @property
    def title(self):
        return self.state.__title

    @property
    def state(self):
        with self.lock:
            return self.__state

    @state.setter
    def state(self, newState):
        with self.lock:
            self.__state = newState

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
        if command is not None and len(command) > 0:
            with self.__commandsLock:
                if not self.onCommandReceived(command):
                    self.__commandsStack.append(command)
                    self.__commandsStack.notify_all()

    def run(self, runMode = RUNMODE_NEW_THREAD):
        with self.lock:
            if self.__state.status != NOT_STARTED:
                raise OperationError('operation already started')
            if runMode not in (self.RUNMODE_THIS_THREAD, self.RUNMODE_NEW_THREAD):
                raise OperationError('invalid run mode')
            self.__runMode = runMode

            if runMode == self.RUNMODE_THIS_THREAD:
                self.__work()
            elif runMode == self.RUNMODE_NEW_THREAD:
                workThread = Thread(target=self.__work)
                workThread.start()

    def sendPause(self):
        self.sendCommand(self.PAUSE_COMMAND)

    def sendResume(self):
        self.sendCommand(self.RESUME_COMMAND)

    def sendCancel(self):
        self.sendCommand(self.CANCEL_COMMAND)

    def togglePauseResume(self):
        with self.lock:
            if self.state.status == RUNNING:
                self.sendPause()
            elif self.state.status == PAUSED:
                self.sendResume()

    def waitForFinish(self):
        """
        Block current thread until operation finished
        """
        with self.__waitFinish:
            self.__waitFinish.wait_for(lambda: self.state.isFinished)

    def waitForResult(self):
        with self.__waitResults:
            if not self.state.isFinished:
                self.__waitResults.wait()

    ## following methods are only for operation code

    def takeCommand(self):
        with self.__commandsLock:
            return self.__commandsStack.pop(0) if len(self.__commandsStack) > 0 else None

    def waitForCommand(self):
        with self.__waitCommand:
            if len(self.__commandsStack) > 0:
                return self.__commandsStack.pop(0)
            else:
                self.__waitCommand.wait_for(lambda: len(self.__commandsStack) > 0 or self.state.isFinished)
                return self.__commandsStack.pop(0) if len(self.__commandsStack) > 0 else None

    def complete(self):
        with self.lock:
            if not self.state.isFinished:
                self.setStatus(FAILED if self.state.errorCount > 0 else COMPLETED)

    def cancel(self):
        with self.lock:
            if not self.state.isFinished:
                self.setStatus(CANCELLED)

    def doWork(self):
        """
        This method should be reimplemented to contain operation code.
        """
        raise NotImplementedError()

    def onCommandReceived(self, command):
        """
        This method is called before received command will be placed into queue.
        If method returns true, command will be considered as executed and will
        not be placed into queue.
        This method is always executed in context of thread that sends command.
        """
        return False

    def __work(self):
        with self.lock:
            if self.state.status != NOT_STARTED:
                raise OperationError('operation already had been started')
            self.setStatus(RUNNING)
            self.__requestDoWork = True
            while not self.state.isFinished:
                if self.__requestDoWork:
                    self.__requestDoWork = False
                    try:
                        self.lock.release()
                        self.doWork()
                    finally:
                        self.lock.acquire()
                    QApplication.processEvents()
                else:
                    self.finish()

    def __setStateAttribute(self, attrib_name, value):
        with self.lock:
            if getattr(self.state, attrib_name) != value:
                setattr(self.state, attrib_name, value)
                self.stateChanged.emit(self.state)
                attrib_signal = attrib_name + 'Changed'
                getattr(self, attrib_signal).emit(value)

    def setStatus(self, newStatus):
        with self.lock:
            if not self.state.isFinished and self.state.status != newStatus:
                self.__setStateAttribute('status', newStatus)

                if self.state.isFinished:
                    self.__waitFinish.notify_all()

                    try:
                        self.__waitCommand.notify_all()
                    except RuntimeError:
                        pass

                    try:
                        self.__waitResults.notify_all()
                    except RuntimeError:
                        pass

                    self.finished.emit(self.state.status)

    def setProgress(self, newProgress):
        self.__setStateAttribute('progress', newProgress)

    def setProgressText(self, newProgressText):
        self.__setStateAttribute('progressText', newProgressText)

    def setCanPause(self, newCanPause):
        self.__setStateAttribute('canPause', newCanPause)

    def setCanCancel(self, newCanCancel):
        self.__setStateAttribute('canCancel', newCanCancel)

    def addResult(self, newResultName, newResultValue):
        with self.lock:
            if not self.state.isFinished:
                self.state.results[newResultName] = newResultValue
                self.__waitResults.notify_all()
                self.stateChanged.emit(self.state)
                self.newResult.emit(newResultName, newResultValue)

    def addMessage(self, message, level):
        with self.lock:
            if not self.state.isFinished:
                self.state.messages.append((message, level))
                if level >= logging.ERROR:
                    self.state.errorCount += 1
                elif level == logging.WARNING:
                    self.state.errorCount += 1

                self.stateChanged.emit(self.state)
                if level >= logging.ERROR:
                    self.errorCountIncreased.emit(self.state.errorCount)
                elif level == logging.WARNING:
                    self.warningCountIncreased.emit(self.state.warningCount)

    def executeSubOperation(self, subop, progressWeigth = 0.0, processResults = False,
                            resultNameConverter = None):
        """
        Operation can execute sub-operation in its context. Operation that executes sub-operation
        is called parent of it.
        No new thread will be created for sub-operation. So this method will return control only after
        sub-operation finish.
        When sub-operation will be finished, progress of parent operation increases on progressWeigth
        percents. During executing of sub-operation parent progress will change from its value at moment
        of calling this method to this value + progressWeigth.
        Changing sub-operation progress text will cause parent operation progress text to be changed to
        sub-operation progress text.
        Before executing sub-operation parent operation canPause flag will be set to sub-operation
        canPause flag value and restored after finishing. Parent canCancel flag will remain the same.
        Messages logged by sub-operation will be logged to parent-operation also.

        If current operation state is PAUSED, it will be resumed.

        If processResults is True, results generated by sub-operation will be added to parent operation too
        """

        with self.lock:
            if self.state.isFinished:
                raise OperationError('cannot execute sub-operation in context of finished operation')
            if subop is None or subop.state.status != NOT_STARTED:
                raise OperationError('invalid sub-operation: should be alive and not started')

            if progressWeigth < 0.0:
                progressWeigth = 0.0;
            elif progressWeigth > 100.0:
                progressWeigth = 100.0;

            self.__subOperation = subop
            self.__subOperationProgressBase = self.state.progress
            self.__subOperationProgressWeight = progressWeigth

            old_can_pause = self.state.canPause
            self.setCanPause(subop.state.canPause)

            old_can_cancel = self.state.canCancel
            self.setCanCancel(self.state.canCancel and subop.canCancel)

            old_progress_text = self.state.progressText
            self.setProgressText(subop.state.progressText)

            self.setStatus(RUNNING)
            if self.state.progress + progressWeigth > 100.0:
                # decrease current progress if need
                self.setProgress(100.0 - progressWeigth)

            subop.progressChanged.connect(self.__onSubopProgress, QtCore.Qt.DirectConnection)
            subop.progressTextChanged.connect(self.setProgressText, QtCore.Qt.DirectConnection)
            subop.messageAdded.connect(self.addMessage, QtCore.Qt.DirectConnection)
            subop.canPauseChanged.connect(self.canPauseChanged, QtCore.Qt.DirectConnection)
            subop.canCancelChanged.connect(lambda canCancel: self.setCanCancel(self.state.canCancel and canCancel),
                                           QtCore.Qt.DirectConnection)
            subop.statusChanged.connect(self.__onSubopStatus, QtCore.Qt.DirectConnection)

            if processResults:
                if resultNameConverter is not None:
                    subop.newResult.connect(lambda k, v: self.addResult(resultNameConverter(k), v),
                                            QtCore.Qt.DirectConnection)
                else:
                    subop.newResult.connect(self.addResult, QtCore.Qt.DirectConnection)

            subop.run(self.RUNMODE_THIS_THREAD)

            self.setCanPause(old_can_pause)
            self.setCanCancel(old_can_cancel)
            self.setProgress(self.__subOperationProgressBase + self.__subOperationProgressWeight)
            self.setProgressText(old_progress_text)

            return subop.state.status

    def __onSubopProgress(self, np):
        self.setProgress(self.__subOperationProgressBase + np * (self.__subOperationProgressWeight / 100.0))

    def __onSubopStatus(self, status):
        if status == RUNNING or status == PAUSED:
            self.setStatus(status)

    def requestGuiCallback(self, callback, *callbackArgs):
        """
        This method allows operation to request executing a piece of code in
        context of user (gui) thread. Method blocks current thread until
        given callback return.
        Returns tuple (accepted, result).
        """
        if callback is None or not callable(callback):
            raise TypeError('callable expected')

        # check if we are in gui thread already. In this case just invoke callback
        if current_thread() == constants.gui_thread:
            return (true, callback(*callbackArgs))
        else:
            with self.__userCallbackLock:
                self.__callbackProcessed = False
                self.__callbackAccepted = False
                self.__callbackResult = None
                reqEvent = _CallbackRequestEvent(self, callback, *callbackArgs)
                QCoreApplication.postEvent(_GuiDispatcher(), reqEvent)
                self.__waitUserCallback.wait_for(lambda: self.__callbackProcessed)
                return (self.__callbackAccepted, self.__callbackResult)

    def reportCallbackProcessed(self, accepted, result = None):
        with self.__userCallbackLock:
            self.__callbackProcessed = True
            self.__callbackAccepted, self.__callbackResult = accepted, result
            self.__waitUserCallback.notify_all()

class WrapperOperation(Operation):
    RESULT_NAME = 'return_value'

    def __init__(self, callable = None, title=''):
        super().__init__(title)
        self.__callable = callable

    def doWork(self):
        try:
            if self.__callable != None:
                self.addResult(self.RESULT_NAME, self.__callable())
        except:
            raise
        finally:
            self.complete()

class DelayOperation(Operation):
    """
    Operation that executes at least given given number
    of milliseconds and does nothing.
    """

    def __init__(self, delay):
        super().__init__('delay for {0} seconds'.format(delay))
        self.__delay = delay

    def doWork(self):
        QTimer.singleShot(self.__delay, self.complete)

class InlineOperation(Operation):
    """
    This is helper class which allows executing of operations
    that are not implemented as a derived class.
    """

    def __init__(self, title):
        super().__init__(title)

    def doWork(self):
        pass