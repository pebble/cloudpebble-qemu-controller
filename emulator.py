__author__ = 'katharine'

import gevent.pool
import tempfile
import settings
import socket
import subprocess
import itertools

_used_displays = set()
def _find_display():
    for i in itertools.count():
        if i not in _used_displays:
            _used_displays.add(i)
            return i

def _free_display(display):
    _used_displays.remove(display)


class Emulator(object):
    def __init__(self, token, debug=False):
        if debug and not settings.DEBUG_ENABLED:
            raise Exception("Can't enable debug without DEBUG_ENABLED set.")
        self.token = token
        self.qemu = None
        self.pkjs = None
        self.gdbserver = None
        self.gdb = None
        self.console_port = None
        self.bt_port = None
        self.ws_port = None
        self.spi_image = None
        self.vnc_display = None
        self.vnc_ws_port = None
        self.gdbserver_port = None
        self.gdb_ws_port = None
        self.group = None
        self.debug = debug

    def run(self):
        self.group = gevent.pool.Group()
        self._choose_ports()
        self._make_spi_image()
        self._spawn_qemu()
        gevent.sleep(4)  # wait for the pebble to boot.
        if self.debug:
            self._spawn_gdb()
        self._spawn_pkjs()

    def kill(self):
        self.spi_image.close()
        if self.qemu is not None:
            self.qemu.terminate()
        if self.pkjs is not None:
            self.pkjs.terminate()
        if self.gdbserver is not None:
            self.gdbserver.terminate()
        if self.gdb is not None:
            self.gdb.terminate()
        self.group.kill()

    def is_alive(self):
        if self.qemu is None or self.pkjs is None:
            return False
        return self.qemu.poll() is None and self.pkjs.poll() is None

    def _qemu_image(self):
        if self.debug:
            return settings.QEMU_MICRO_IMAGE
        else:
            return settings.QEMU_MICRO_IMAGE_NOWATCHDOG

    def _choose_ports(self):
        self.console_port = self._find_port()
        self.bt_port = self._find_port()
        self.ws_port = self._find_port()
        self.vnc_display = self._find_port() - 5900  # correct for the VNC 5900+n convention
        self.vnc_ws_port = self._find_port()
        if self.debug:
            self.qemu_gdb_port = self._find_port()
            self.gdbserver_port = self._find_port()
            self.gdb_ws_port = self._find_port()

    def _make_spi_image(self):
        self.spi_image = tempfile.NamedTemporaryFile()
        with open(settings.QEMU_SPI_IMAGE) as f:
            self.spi_image.write(f.read())
        self.spi_image.flush()


    @staticmethod
    def _find_port():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('localhost', 0))
        addr, port = s.getsockname()
        s.close()
        return port

    def _spawn_qemu(self):
        if settings.SSL_ROOT is not None:
            x509 = ",x509=%s" % settings.SSL_ROOT
        else:
            x509 = ""
        qemu_params = [
            "-rtc", "base=localtime",
            "-cpu", "cortex-m3",
            "-pflash", self._qemu_image(),
            "-mtdblock", self.spi_image.name,
            "-serial", "null",  # These are logs that nothing actually logs to.
            "-serial", "tcp:127.0.0.1:%d,server,nowait" % self.bt_port,   # Used for bluetooth data
            "-serial", "tcp:127.0.0.1:%d,server,nowait" % self.console_port,   # Used for console
            "-monitor", "stdio",
            "-machine", "pebble-bb2",
            "-vnc", ":%d,password,websocket=%d%s" % (self.vnc_display, self.vnc_ws_port, x509)
        ]
        if self.debug:
            qemu_params.extend(["-gdb", "tcp:127.0.0.1:%d" % self.qemu_gdb_port])
        self.qemu = subprocess.Popen([settings.QEMU_BIN] + qemu_params,
                                     cwd=settings.QEMU_DIR,
                                     stdout=None,
                                     stdin=subprocess.PIPE,
                                     stderr=None)
        self.qemu.stdin.write("change vnc password\n")
        self.qemu.stdin.write("%s\n" % self.token[:8])
        self.group.spawn(self.qemu.communicate)

    def _spawn_pkjs(self):
        if settings.SSL_ROOT is not None:
            ssl_args = ['--ssl-root', settings.SSL_ROOT]
        else:
            ssl_args = []
        self.pkjs = subprocess.Popen([
            "%s/bin/python" % settings.PKJS_VIRTUALENV, settings.PKJS_BIN,
            '--qemu', '127.0.0.1:%d' % self.bt_port,
            '--port', str(self.ws_port),
            '--token', self.token
        ] + ssl_args)
        self.group.spawn(self.pkjs.communicate)

    def _spawn_gdb(self):
        # We need a gdbserver first...
        self.gdbserver = subprocess.Popen([
            settings.GDBSERVER_BIN,
            "--port=%d" % self.gdbserver_port,
            "--target=127.0.0.1:%d" % self.qemu_gdb_port,
        ])
        self.group.spawn(self.gdbserver.communicate)

        self.gdb = subprocess.Popen([
            settings.CLOUDPEBBLE_GDB_BIN,
            "--gdbserver", "127.0.0.1:%d" % self.gdbserver_port,
            "--port", str(self.gdb_ws_port),
            "--token ", self.token,
        ])
        self.group.spawn(self.gdb.communicate)