#!/usr/bin/env python
__author__ = 'katharine'

import gevent.monkey
gevent.monkey.patch_all(subprocess=True)
import gevent
import gevent.pool
from flask import Flask, request, jsonify, abort
from flask.ext.cors import CORS
from time import time as now

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
import geventwebsocket
import websocket

import settings
from emulator import Emulator
from uuid import uuid4, UUID
import atexit

app = Flask(__name__)
cors = CORS(app, headers=["X-Requested-With", "X-CSRFToken", "Content-Type"], resources="/qemu/*")


emulators = {}

@app.route('/qemu/launch', methods=['POST'])
def launch():
    if request.headers.get('authorization', None) != settings.LAUNCH_AUTH_HEADER:
        abort(403)
    if len(emulators) >= settings.EMULATOR_LIMIT:
        abort(503)
    uuid = uuid4()
    emu = Emulator(request.form['token'])
    emulators[uuid] = emu
    emu.last_ping = now()
    emu.run()
    return jsonify(uuid=uuid, ws_port=emu.ws_port, vnc_display=emu.vnc_display, vnc_ws_port=emu.vnc_ws_port)

@app.route('/qemu/<emu>/ping', methods=['POST'])
def ping(emu):
    try:
        emu = UUID(emu)
    except ValueError:
        abort(404)
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


@app.route('/qemu/<emu>/kill', methods=['POST'])
def kill(emu):
    try:
        emu = UUID(emu)
    except ValueError:
        abort(404)
    if emu in emulators:
        emulators[emu].kill()
    del emulators[emu]
    return jsonify(status='ok')


def proxy_ws(emu, attr):
    server_ws = request.environ.get('wsgi.websocket', None)
    if server_ws is None:
        return "websocket endpoint", 400

    try:
        emulator = emulators[emu]
    except ValueError:
        abort(404)
        return  # unreachable but makes IDE happy.
    client_ws = websocket.create_connection("wss://localhost:%d/" % getattr(emulator, attr))
    alive = [True]

    def do_recv(a, b):
        try:
            while alive[0]:
                b.send(a.recv())
        except (websocket.WebSocketException, geventwebsocket.WebSocketError):
            alive[0] = False

    print 'spawning relays'
    group = gevent.pool.Group()
    group.spawn(do_recv, server_ws, client_ws)
    group.spawn(do_recv, client_ws, server_ws)
    group.join()
    print 'relays exited'

@app.route('/qemu/<emu>/ws/phone')
def ws_phone(emu):
    proxy_ws(emu, 'ws_port')

@app.route('/qemu/<emu>/ws/vnc')
def ws_vnc(emu):
    proxy_ws(emu, 'vnc_ws_port')


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
    server = pywsgi.WSGIServer(('', 5000), app, handler_class=WebSocketHandler)
    server.serve_forever()
