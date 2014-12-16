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
    def __init__(self, token):
        self.token = token
        self.qemu = None
        self.pkjs = None
        self.console_port = None
        self.bt_port = None
        self.ws_port = None
        self.spi_image = None
        self.vnc_display = None
        self.vnc_ws_port = None
        self.group = None

    def run(self):
        self.group = gevent.pool.Group()
        self._choose_ports()
        self._make_spi_image()
        self._spawn_qemu()
        gevent.sleep(3)  # wait for the pebble to boot.
        self._spawn_pkjs()

    def kill(self):
        if self.qemu is not None:
            self.qemu.terminate()
        if self.pkjs is not None:
            self.pkjs.terminate()
        self.group.kill()

    def is_alive(self):
        if self.qemu is None or self.pkjs is None:
            return False
        return self.qemu.poll() is None and self.pkjs.poll() is None

    def _choose_ports(self):
        self.console_port = self._find_port()
        self.bt_port = self._find_port()
        self.ws_port = self._find_port()
        self.vnc_display = self._find_port() - 5900
        self.vnc_ws_port = self._find_port()

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
        self.qemu = subprocess.Popen([
            settings.QEMU_BIN,
            "-rtc", "base=localtime",
            "-cpu", "cortex-m3",
            "-pflash", settings.QEMU_MICRO_IMAGE,
            "-mtdblock", settings.QEMU_SPI_IMAGE,
            "-serial", "file:uart1.log",  # this isn't useful, but...
            "-serial", "tcp:127.0.0.1:%d,server,nowait" % self.bt_port,   # Used for bluetooth data
            "-serial", "tcp:127.0.0.1:%d,server,nowait" % self.console_port,   # Used for console
            "-monitor", "stdio",
            "-machine", "pebble-bb2",
            "-vnc", ":%d,password,websocket=%d" % (self.vnc_display, self.vnc_ws_port)
        ], cwd=settings.QEMU_DIR, stdout=None, stdin=subprocess.PIPE, stderr=None)
        self.qemu.stdin.write("change vnc password\n")
        self.qemu.stdin.write("%s\n" % self.token[:8])
        self.group.spawn(self.qemu.communicate)

    def _spawn_pkjs(self):
        self.pkjs = subprocess.Popen([
            "%s/bin/python" % settings.PKJS_VIRTUALENV, settings.PKJS_BIN,
            '127.0.0.1:%d' % self.bt_port,
            str(self.ws_port),
            self.token
        ])
        self.group.spawn(self.pkjs.communicate)
