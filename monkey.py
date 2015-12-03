import gevent
import os
import shutil
import tempfile
import subprocess
from zipfile import ZipFile

class Monkey():
    def __init__(self, archive):
        # TODO: DON'T HARDCODE THESE
        self.loghash_path = '/home/vagrant/loghash/loghash_dict.json'
        self.runner_path = '/home/vagrant/pebble-test/runner.py'

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

        # TODO: consider the name
        self.runner = subprocess.Popen(['/usr/bin/env', 'python', self.runner_path, 'monkey'],
                                       cwd=self.tempdir,
                                       env=env)

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

