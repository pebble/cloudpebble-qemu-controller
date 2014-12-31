__author__ = 'katharine'

from os import environ as env
import multiprocessing

LAUNCH_AUTH_HEADER = env.get('LAUNCH_AUTH_HEADER', 'secret')
EMULATOR_LIMIT = int(env.get('EMULATOR_FIXED_LIMIT', multiprocessing.cpu_count() * 3 - 2))
QEMU_DIR = env['QEMU_DIR']
QEMU_BIN = env.get('QEMU_BIN', 'qemu-system-arm')
PKJS_BIN = env.get('PKJS_BIN', 'jskit.py')
PKJS_VIRTUALENV = env['PKJS_VIRTUALENV']
QEMU_MICRO_IMAGE = env['QEMU_MICRO_IMAGE']
QEMU_SPI_IMAGE = env['QEMU_SPI_IMAGE']
SSL_ROOT = env.get('SSL_ROOT', None)
DEBUG_ENABLED = 'GDB_DEBUG_ENABLED' in env
if DEBUG_ENABLED:
    QEMU_MICRO_IMAGE_NOWATCHDOG = env['QEMU_MICRO_IMAGE_NOWATCHDOG']
    GDBSERVER_BIN = env['QEMU_GDBSERVER_PROXY_BIN']
    CLOUDPEBBLE_GDB_BIN = env['CLOUDPEBBLE_GDB_BIN']

PORT = int(env.get('QCON_PORT', 5001))
HOST = env.get('QCON_HOST', '0.0.0.0')

DEBUG = 'DEBUG' in env
