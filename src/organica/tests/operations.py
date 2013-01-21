import unittest
import uuid
import logging

from organica.utils.operations import Operation, OperationState, globalOperationContext, WrapperOperation


class GenerateUuidsOperation(Operation):
    def __init__(self):
        Operation.__init__(self, 'gen_uuids')
        self.count = 0

    def doWork(self):
        for i in range(100):
            self.addResult('uuid_{0}_{1}'.format(self.count, i), uuid.uuid4())
        self.count += 1
        self.requestDoWork = self.count < 10


class TestOperation(unittest.TestCase):
    def test(self):
        op = GenerateUuidsOperation()
        self.assertEqual(op.title, 'gen_uuids')
        self.assertEqual(op.state.status, OperationState.NOT_STARTED)
        self.assertEqual(op.state.progress, 0)
        self.assertEqual(op.runMode, Operation.RUNMODE_NOT_STARTED)

        op.run(Operation.RUNMODE_NEW_THREAD)
        final_status = op.waitForFinish()
        self.assertEqual(op.state.status, OperationState.COMPLETED)
        self.assertEqual(op.state.status, final_status)
        self.assertEqual(len(op.state.results), 1000)
        self.assertEqual(op.runMode, Operation.RUNMODE_NEW_THREAD)

        with globalOperationContext().newOperation('test_op') as op:
            self.assertEqual(op.title, 'test_op')
            self.assertEqual(op.state.status, OperationState.RUNNING)

        self.assertTrue(op.state.isFinished)
        self.assertEqual(op.state.status, OperationState.COMPLETED)

        try:
            with globalOperationContext().newOperation('test_op') as op:
                raise TypeError('test_error')
        except TypeError:
            pass
        else:
            self.assertTrue(False)

        self.assertTrue(op.state.isFinished)
        self.assertEqual(op.state.status, OperationState.FAILED)
        self.assertEqual(op.state.progress, 100)

        with globalOperationContext().newOperation('test_op') as op:
            op.setProgress(10.0)
            self.assertEqual(op.state.progress, 10.0)

            op.setProgress(100.0)
            self.assertEqual(op.state.progress, 100.0)

            self.assertRaises(TypeError, op.setProgress, 120.0)
            self.assertEqual(op.state.progress, 100.0)

            op.setProgressText('working')
            self.assertEqual(op.state.progressText, 'working')

            op.setCanPause(True)
            self.assertEqual(op.state.canPause, True)
            op.setCanPause(False)

            op.setCanCancel(True)
            self.assertEqual(op.state.canCancel, True)
            op.setCanCancel(False)

            op.addMessage('error occupied', logging.ERROR)
            self.assertEqual(op.state.errorCount, 1)
            self.assertEqual(op.state.messages, [('error occupied', logging.ERROR)])

            op.addMessage('warning', logging.WARNING)
            self.assertEqual(op.state.errorCount, 1)
            self.assertEqual(op.state.warningCount, 1)
            self.assertEqual(op.state.messages, [('error occupied', logging.ERROR),
                                                 ('warning', logging.WARNING)])

            op.setProgress(20)

            with globalOperationContext().newOperation('sub-operation', progress_weight=40) as subop:
                subop.setCanPause(True)   # parent -> True
                subop.setCanCancel(True)  # parent -> False

                self.assertEqual(op.state.progress, 20)
                self.assertEqual(op.state.canPause, True)
                self.assertEqual(op.state.canCancel, False)
                self.assertEqual(op.state.progressText, 'working')

                subop.setProgress(50)
                self.assertEqual(op.state.progress, 40)  # 20 + 40 * (50 / 100)

                subop.setProgressText('sub task')
                self.assertEqual(op.state.progressText, 'sub task')

                subop.addResult('sub-result', 'result_value')
                self.assertEqual(len(subop.state.results), 1)
                self.assertEqual(len(op.state.results), 0)

            # sub operation finished
            self.assertEqual(op.state.canPause, False)
            self.assertEqual(op.state.canCancel, False)
            self.assertEqual(op.state.progress, 60)  # 20 + 40
            self.assertEqual(op.state.progressText, 'working')
            self.assertEqual(len(op.state.results), 0)

            op.sendPause()
            self.assertEqual(op.takeCommand(), Operation.PAUSE_COMMAND)

        def some_function():
            return 2 * 2

        wrapper_operation = WrapperOperation(some_function)
        wrapper_operation.run()
        wrapper_operation.waitForFinish()
        self.assertEqual(wrapper_operation.state.results['result'], 4)
