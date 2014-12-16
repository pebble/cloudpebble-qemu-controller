__author__ = 'katharine'

from os import environ as env

EMULATOR_LIMIT = env.get('EMULATOR_LIMIT', 2)
QEMU_DIR = env['QEMU_DIR']
QEMU_BIN = env.get('QEMU_BIN', 'qemu-system-arm')
PKJS_BIN = env.get('PKJS_BIN', 'jskit.py')
PKJS_VIRTUALENV = env['PKJS_VIRTUALENV']
QEMU_MICRO_IMAGE = env['QEMU_MICRO_IMAGE']
QEMU_SPI_IMAGE = env['QEMU_SPI_IMAGE']

PORT = int(env.get('QCON_PORT', 5001))
HOST = env.get('QCON_HOST', '0.0.0.0')

DEBUG = 'DEBUG' in env
