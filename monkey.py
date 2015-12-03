import gevent
import os
import shutil
import tempfile
import subprocess
import settings
from zipfile import ZipFile


class Monkey():
    def __init__(self, archive):
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

        with ZipFile(archive) as zip:
            zip.extractall(self.tempdir)
        print "Extracted to %s " % self.tempdir

    def make_environment(self, port):
        env = os.environ.copy()
        env['PEBBLE_LOGHASH_DICT'] = self.loghash_path
        env['PEBBLE_VIRTUAL_ONLY'] = '1'
        env['PEBBLE_DEVICE'] = 'socket://localhost:{}'.format(port)
        return env

    def wait(self):
        self.runner.communicate()
        self.runner = None
        self.clean()
        self.thread = None


    def run(self, console_port):
        env = self.make_environment(console_port)
        args = [self.runner_path, 'monkey']
        self.runner = subprocess.Popen(args, cwd=self.tempdir, env=env)
        self.thread = gevent.spawn(self.wait)

    def clean(self):
        if self.tempdir:
            shutil.rmtree(self.tempdir)
            self.tempdir = None

    def kill(self):
        if self.runner:
            if self.runner.poll() is not None:
                self.runner.kill()
            self.runner = None
        if self.thread:
            self.thread.wait()

    def is_alive(self):
        return self.runner is not None and self.thread is not None and self.runner.poll() is None

