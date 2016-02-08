import gevent
import os
import shutil
import tempfile
import subprocess
import settings
import requests
from zipfile import ZipFile

class Monkey():
    def __init__(self, archive, console_port, bt_port, callback_url):
        """ Set up a Monkey test

        :param archive: a file or filename which can be opened by ZipFile
        :param console_port: The console port of the QEMU emulator to connect to
        :param callback_url: A URL to post the results to
        """
        self.loghash_path = settings.PEBBLE_LOGHASH_DICT
        self.runner_path = settings.PEBBLE_TEST_BIN
        if not self.loghash_path or not self.runner_path:
            variables = " and ".join(x for x in [
                'PEBBLE_LOGHASH_DICT' if not self.loghash_path else None,
                'PEBBLE_TEST_BIN' if not self.runner_path else None]
                if x)
            raise Exception("Cannot run test, %s not set." % variables)
        self.tempdir = tempfile.mkdtemp()
        self.thread = None
        self.runner = None
        self.console_port = console_port
        self.bt_port = bt_port
        self.callback_url = callback_url
        self.subscriptions = []
        with ZipFile(archive) as zip:
            zip.extractall(self.tempdir)

    def make_environment(self):
        """ :return: A copy of the current runtime environment plus the variables needed for runner.py """
        env = os.environ.copy()
        env['PEBBLE_LOGHASH_DICT'] = self.loghash_path
        env['PEBBLE_VIRTUAL_ONLY'] = '1'
        env['PEBBLE_DEVICE'] = 'socket://localhost:{}'.format(self.console_port)
        env['PEBBLE_BT_DEVICE'] = 'socket://localhost:{}'.format(self.bt_port)
        return env

    def notify_cloudpebble(self, code, log):
        """ Notify cloudpebble of the result and log output of the test

        :param code: runner.py process return code
        :param log: runner.py STDOUT
        """
        if code == 0:
            status = 'passed'
        elif code == 1:
            status = 'failed'
        else:
            status = 'error'
        data = {'log': log, 'status': status, 'token': settings.LAUNCH_AUTH_HEADER}
        requests.post(self.callback_url, data=data)

    def wait(self):
        """ Gevent thread. Wait for the runner to complete, then notifies CloudPebble and cleans up. """
        try:
            output = []
            try:
                for line in self.runner.stdout:
                    output.append(line.strip())
                    for q in self.subscriptions:
                        q.put(line.strip())

                code = self.runner.wait() if self.runner else 1
                output.extend(['', "Process terminated with code: %s" % code])
                for q in self.subscriptions:
                    q.put('')
                    q.put(output[-1])
            finally:
                for q in self.subscriptions:
                    q.put(StopIteration)

            stdout = "\n".join(output)
            self.runner = None
        finally:
            self.clean()
            self.thread = None

        self.notify_cloudpebble(code, stdout)

    def subscribe(self, queue):
        self.subscriptions.append(queue)

    def run(self):
        """ Starts the test """
        if self.is_alive():
            return
        env = self.make_environment()
        # --ff is fail-fast, needed because runner.py doesn't return a correct failure code without it.
        # TODO: remove --ff when bug the is fixed
        args = [self.runner_path, 'monkey', '--ff']
        self.runner = subprocess.Popen(args, cwd=self.tempdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.thread = gevent.spawn(self.wait)

    def clean(self):
        """ Delete the temporary directory containing the test files, if it exists """
        if self.tempdir:
            shutil.rmtree(self.tempdir)
            self.tempdir = None
        else:
            print "Failed to delete temporary directory \"%s\"" % self.tempdir

    def kill(self):
        """ Kill the test runner process and its greenlet """
        self.subscriptions = []
        if self.runner:
            self.runner.kill()
            self.runner = None
        if self.thread:
            self.thread.join()
            self.thread = None

    def is_alive(self):
        """ :return: True if the test runner is still alive """
        return self.runner is not None and self.thread is not None and self.runner.poll() is None

