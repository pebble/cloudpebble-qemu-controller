import gevent
import os
import shutil
import tempfile
import subprocess
import settings
import requests
from zipfile import ZipFile

class Monkey():
    def __init__(self, archive, console_port, callback_url):
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
        self.callback_url = callback_url

        with ZipFile(archive) as zip:
            zip.extractall(self.tempdir)

    def make_environment(self, port):
        env = os.environ.copy()
        env['PEBBLE_LOGHASH_DICT'] = self.loghash_path
        env['PEBBLE_VIRTUAL_ONLY'] = '1'
        env['PEBBLE_DEVICE'] = 'socket://localhost:{}'.format(port)
        return env

    def notify_cloudpebble(self, code, log):
        data = {'log': log, 'code': code, 'token': settings.LAUNCH_AUTH_HEADER}
        requests.post(self.callback_url, data=data)

    def wait(self):
        try:
            stdout, stderr = self.runner.communicate()
            code = self.runner.wait()
            stdout += "\nProcess terminated with code: %s" % code
            self.runner = None
        finally:
            self.clean()
            self.thread = None

        self.notify_cloudpebble(code, stdout)

    def run(self):
        if self.is_alive():
            return
        env = self.make_environment(self.console_port)
        # FIXME: --ff is a workaround the fact that
        args = [self.runner_path, 'monkey', '--ff']
        # TODO: consider the name?
        print "RUNNING %s" % args
        self.runner = subprocess.Popen(args, cwd=self.tempdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.thread = gevent.spawn(self.wait)

    def clean(self):
        if self.tempdir:
            shutil.rmtree(self.tempdir)
            self.tempdir = None
        else:
            print "Failed to delete temporary directory \"%s\"" % self.tempdir

    def kill(self):
        if self.runner:
            if self.runner.poll() is not None:
                self.runner.kill()
            self.runner = None
        if self.thread:
            self.thread.join()
            self.thread = None

    def is_alive(self):
        return self.runner is not None and self.thread is not None and self.runner.poll() is None

