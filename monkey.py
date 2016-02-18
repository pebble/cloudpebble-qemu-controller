import gevent
import os
import shutil
import tempfile
import subprocess
import requests
from zipfile import ZipFile


class Monkey():
    def __init__(self, archive):
        """ Set up a Monkey test
        :param archive: a file or filename which can be opened by ZipFile
        """
        # self.loghash_path = settings.PEBBLE_LOGHASH_DICT
        # self.runner_path = settings.PEBBLE_TEST_BIN

        self.tempdir = tempfile.mkdtemp()
        self.thread = None
        self.runner = None
        self.subscriptions = []
        with ZipFile(archive) as zip_file:
            zip_file.extractall(self.tempdir)

    @staticmethod
    def make_environment(loghash_path, console_port, bt_port, serial_filename=None):
        """ Make a copy of the current runtime environment plus the variables needed for runner.py
        :param serial_filename: Filename for pbltest to output a serial log to, or None
        :param loghash_path: Path to loghash_dict.json
        :param console_port: The console port of the QEMU emulator to connect to
        :param bt_port: The bluetooth port of the QEMU emulator
        :return: a dictionary of key/value pairs
        """
        env = os.environ.copy()
        env['PEBBLE_LOGHASH_DICT'] = loghash_path
        env['PEBBLE_VIRTUAL_ONLY'] = '1'
        env['PEBBLE_DEVICE'] = 'socket://localhost:{}'.format(console_port)
        env['PEBBLE_BT_DEVICE'] = 'socket://localhost:{}'.format(bt_port)
        if serial_filename:
            print "Outputting serial log to {}".format(serial_filename)
            env['PEBBLE_SERIAL_LOG'] = serial_filename
        return env

    @staticmethod
    def notify_cloudpebble(callback_url, code, log, launch_auth_header):
        """ Notify cloudpebble of the result and log output of the test
        :param code: runner.py process return code
        :param log: runner.py STDOUT
        :param launch_auth_header: Authorisation header for notifying cloudpebble of results
        """
        if code == 0:
            status = 'passed'
        elif code == 1:
            status = 'failed'
        else:
            status = 'error'
        data = {'log': log, 'status': status, 'token': launch_auth_header}
        requests.post(callback_url, data=data)

    def wait(self, update, callback_url=None, launch_auth_header=None):
        """ Gevent thread. Wait for the runner to complete, then notifies CloudPebble and cleans up.
        :param update: True if we should look for new screenshots after the run finishes
        :param callback_url: A URL to post the results to
        """
        output = []
        try:
            # record test output and and send it to subscription queues
            for line in self.runner.stdout:
                output.append(line.strip())
                for q in self.subscriptions:
                    q.put(line.strip())

            # when the pipe is closed, wait on the runner process
            code = self.runner.wait() if self.runner else 1

            # Write the process termination code to the output
            output.extend(['', "Process terminated with code: %s" % code])
            for q in self.subscriptions:
                q.put('')
                q.put(output[-1])

        finally:
            # Always clean up
            self.clean()

        std_out = "\n".join(output)

        if launch_auth_header and callback_url:
            self.notify_cloudpebble(callback_url, code, std_out, launch_auth_header)
        else:
            print std_out

    def subscribe(self, queue):
        self.subscriptions.append(queue)

    @staticmethod
    def check_run_arguments(runner_path, loghash_path):
        if not loghash_path or not runner_path:
            variables = " and ".join(x for x in [
                'PEBBLE_LOGHASH_DICT' if not loghash_path else None,
                'PEBBLE_TEST_BIN' if not runner_path else None]
                if x)
            raise Exception("Cannot run test, %s not set." % variables)

    def run(self, runner_path, loghash_path, console_port, bt_port, callback_url=None, launch_auth_header=None, debug=True, update=True, block=False):
        """ Run a test
        :param runner_path: Path to runner.py
        :param loghash_path: Path to loghash_dict.json
        :param console_port: The console port of the QEMU emulator to connect to
        :param bt_port: The bluetooth port of the QEMU emulator
        :param callback_url: A URL to post the results to
        :param launch_auth_header: Authorisation header for notifying cloudpebble of results
        :param debug: Whether to output full serial logs
        :param update: Whether to output new screenshots
        :param block: Whether to block or run in a greenlet
        """
        self.check_run_arguments(runner_path, loghash_path)
        if self.is_alive():
            return

        env = self.make_environment(
                console_port=console_port,
                bt_port=bt_port,
                loghash_path=loghash_path,
                serial_filename=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serial.log')
        )

        # --ff is fail-fast, needed because runner.py doesn't return a correct failure code without it.
        # TODO: remove --ff when bug the is fixed
        args = [runner_path, 'monkey']
        if debug:
            args.append('--debug')
        if update:
            args.append('--update')
        else:
            args.append('--ff')
        if debug:
            print "Executing {}".format(" ".join(args))

        self.runner = subprocess.Popen(args, cwd=self.tempdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if block:
            self.wait(update, callback_url, launch_auth_header=launch_auth_header)
        else:
            self.thread = gevent.spawn(self.wait, update, callback_url, launch_auth_header=launch_auth_header)

    def clean(self):
        """ Delete the temporary directory containing the test files, if it exists """
        if self.tempdir:
            shutil.rmtree(self.tempdir)
            self.tempdir = None
        else:
            print "Failed to delete temporary directory \"%s\"" % self.tempdir

    def kill(self):
        """ Kill the test runner process and its greenlet """
        for q in self.subscriptions:
            q.put(StopIteration)
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

if __name__ == '__main__':
    monkey = Monkey('test_archive.zip')
    monkey.run(os.path.abspath("fake_runner.py"), "loghash_dict.json", "", "", update=True, debug=True, block=True)
