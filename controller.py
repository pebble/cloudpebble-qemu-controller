#!/usr/bin/env python
__author__ = 'katharine'

import gevent.monkey
gevent.monkey.patch_all(subprocess=True)
import gevent
import gevent.pool
from flask import Flask, request, jsonify, abort
from flask.ext.cors import CORS
from time import time as now
import ssl
import os
import pwd
import grp

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


def proxy_ws(emu, attr, subprotocols=[]):
    server_ws = request.environ.get('wsgi.websocket', None)
    if server_ws is None:
        return "websocket endpoint", 400

    try:
        emulator = emulators[UUID(emu)]
    except ValueError as e:
        abort(404)
        return  # unreachable but makes IDE happy.
    target_url = "ws://localhost:%d/" % getattr(emulator, attr)
    try:
        client_ws = websocket.create_connection(target_url, subprotocols=subprotocols)
    except websocket.WebSocketException:
        print "connection to %s failed." % target_url
        import traceback
        traceback.print_exc()
        return 'failed', 500
    alive = [True]
    def do_recv(receive, send):
        try:
            while alive[0]:
                send(receive())
        except (websocket.WebSocketException, geventwebsocket.WebSocketError, TypeError):
            alive[0] = False
        except:
            alive[0] = False
            raise

    group = gevent.pool.Group()
    group.spawn(do_recv, lambda: server_ws.receive(), lambda x: client_ws.send_binary(x))
    group.spawn(do_recv, lambda: bytearray(client_ws.recv()), lambda x: server_ws.send(x))
    group.join()
    return ''

@app.route('/qemu/<emu>/ws/phone')
def ws_phone(emu):
    return proxy_ws(emu, 'ws_port')

@app.route('/qemu/<emu>/ws/vnc')
def ws_vnc(emu):
    return proxy_ws(emu, 'vnc_ws_port', subprotocols=['binary'])


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


def drop_privileges(uid_name='nobody', gid_name='nogroup'):
    if os.getuid() != 0:
        # We're not root so, like, whatever dude
        return

    # Get the uid/gid from the name
    running_uid = pwd.getpwnam(uid_name).pw_uid
    running_gid = grp.getgrnam(gid_name).gr_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(running_gid)
    os.setuid(running_uid)

    # Ensure a very conservative umask
    os.umask(077)

print "Emulator limit: %d" % settings.EMULATOR_LIMIT

if __name__ == '__main__':
    app.debug = settings.DEBUG
    ssl_args = {}
    if settings.SSL_ROOT is not None:
        ssl_args = {
            'keyfile': '%s/server-key.pem',
            'certfile': '%s/server-cert.pem',
            'ca_certs': '%s/ca-cert.pem',
            'ssl_version': ssl.PROTOCOL_TLSv1,
        }
    server = pywsgi.WSGIServer(('', settings.PORT), app, handler_class=WebSocketHandler, **ssl_args)
    server.start()
    if settings.RUN_AS_USER is not None:
        drop_privileges(settings.RUN_AS_USER, settings.RUN_AS_USER)
    server.serve_forever()
