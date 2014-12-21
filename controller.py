#!/usr/bin/env python
__author__ = 'katharine'

import gevent.monkey
gevent.monkey.patch_all(subprocess=True)
import gevent
import gevent.pool
from flask import Flask, request, jsonify, abort
from flask.ext.cors import CORS
from time import time as now

import settings
from emulator import Emulator
from uuid import uuid4
import atexit

app = Flask(__name__)
cors = CORS(app, headers=["X-Requested-With", "X-CSRFToken", "Content-Type"], resources="/qemu/*")


emulators = {}

@app.route('/launch', methods=['POST'])
def launch():
    if len(emulators) >= settings.EMULATOR_LIMIT:
        abort(503)
    uuid = uuid4()
    emu = Emulator(request.form['token'])
    emulators[uuid] = emu
    emu.last_ping = now()
    emu.run()
    return jsonify(uuid=uuid, ws_port=emu.ws_port, vnc_display=emu.vnc_display, vnc_ws_port=emu.vnc_ws_port)

@app.route('/<emu>/ping', methods=['POST'])
def ping(emu):
    if emu not in emulators:
        return jsonify(alive=False)
    if emulators[emu].is_alive():
        emulators[emu].last_ping = now()
        return jsonify(alive=True)
    else:
        try:
            emulators[emu].kill()
        except:
            pass
        del emulators[emu]
        return jsonify(alive=False)

@app.route('/<emu>/kill', methods=['POST'])
def kill(emu):
    if emu in emulators:
        emulators[emu].kill()
    del emulators[emu]
    return jsonify(status='ok')

def _kill_idle_emulators():
    while True:
        for key, emulator in emulators.items():
            if now() - emulator.last_ping > 300:
                print "killing idle emulator %s" % key
                emulator.kill()
                del emulators[key]
        gevent.sleep(60)

idle_killer = gevent.spawn(_kill_idle_emulators)

@atexit.register
def kill_emulators():
    for emulator in emulators.itervalues():
        emulator.kill()
    emulators.clear()

print "Emulator limit: %d" % settings.EMULATOR_LIMIT

if __name__ == '__main__':
    app.debug = settings.DEBUG
    app.run(settings.HOST, settings.PORT)
