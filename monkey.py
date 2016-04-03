import gevent
import os
import shutil
import tempfile
import subprocess
import requests
from zipfile import ZipFile
from ta_utils import find_all_screenshots


class Monkey():
    def __init__(self, archive):
        """ Set up a Monkey test
        :param archive: a file or filename which can be opened by ZipFile
        """

        self.tempdir = tempfile.mkdtemp()
        self.thread = None
        self.runner = None
        self.subscriptions = []
        with ZipFile(archive) as zip_file:
            zip_file.extractall(self.tempdir)

        self.screenshots_before = dict(find_all_screenshots(self.tempdir))

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
    def notify_cloudpebble(callback_url, code, log, launch_auth_header, uploads=None):
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

        files = []

        if uploads:
            platform, new_screenshots = uploads
            for filename in new_screenshots:
                files.append(('uploads[]', (os.path.basename(filename), open(filename, 'rb'), "image/png")))
            data['uploads_platform'] = platform

        requests.post(callback_url, data=data, files=files)

    @staticmethod
    def compare_screenshots(before, after):
        """
        :param before: Dict (platform->files) of screenshots before
        :param after: Dict (platform->files) of screenshots after
        :return: a pair of (platform, set([new_files])), for the single platform with new files
        """
        for platform in after:
            if after[platform]:
                new = after[platform] - before.get(platform, set())
                if new:
                    return platform, new
        return None

    def find_new_screenshots(self):
        screenshots_after = dict(find_all_screenshots(self.tempdir))
        return self.compare_screenshots(self.screenshots_before, screenshots_after)

    def wait(self, update, callback_url=None, launch_auth_header=None):
        """ Gevent thread. Wait for the runner to complete, then notifies CloudPebble and cleans up.
        :param update: True if we should look for new screenshots after the run finishes
        :param callback_url: A URL to post the results to
        :param launch_auth_header: Authorisation header for notifying cloudpebble of results
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
            new_screenshots = self.find_new_screenshots() if update else None
            print "New screenshots:", new_screenshots

            # Write the process termination code to the output
            output.extend(['', "Process terminated with code: %s" % code])
            for q in self.subscriptions:
                q.put('')
                q.put(output[-1])

            std_out = "\n".join(output)

            if launch_auth_header and callback_url:
                self.notify_cloudpebble(callback_url, code, std_out, launch_auth_header, uploads=new_screenshots)
            else:
                print "-----\nlaunch_auth_header={}\ncallback_url={}\nNot notifying cloudpebble\n-----".format(launch_auth_header, callback_url)
                print std_out

        finally:
            # Always clean up
            self.kill()

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

    def run(self, runner_path, loghash_path, console_port, bt_port, callback_url=None, launch_auth_header=None, debug=False, update=False, block=False):
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

        serial_filename = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'serial.log') if debug else None
        env = self.make_environment(
                console_port=console_port,
                bt_port=bt_port,
                loghash_path=loghash_path,
                serial_filename=serial_filename
        )

        # --ff is fail-fast, which makes tests fail immediately upon the first failure
        args = [runner_path, 'monkey']
        if debug:
            args.append('--debug')
        if update:
            args.append('--update')
        else:
            args.append('--ff')
        print " ".join(["RUNNING"] + args)

        self.runner = subprocess.Popen(args, cwd=self.tempdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if block:
            self.wait(update, callback_url, launch_auth_header=launch_auth_header)
        else:
            self.thread = gevent.spawn(self.wait, update, callback_url, launch_auth_header=launch_auth_header)

    def kill(self):
        """ Kill the test runner process and its greenlet and clean up"""
        # Delete the temporary directory containing the test
        if self.tempdir:
            shutil.rmtree(self.tempdir)
            self.tempdir = None

        # End all log subscriptions
        for q in self.subscriptions:
            q.put(StopIteration)
        self.subscriptions = []

        # Kill subprocesses
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
