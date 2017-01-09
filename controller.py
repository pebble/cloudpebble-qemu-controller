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
import sys

from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler
import geventwebsocket
import websocket

import settings
from emulator import Emulator
from uuid import uuid4, UUID
import logging
import atexit

app = Flask(__name__)
cors = CORS(app, headers=["X-Requested-With", "X-CSRFToken", "Content-Type"], resources="/qemu/*")
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s %(asctime)s: %(message)s")

emulators = {}

@app.route('/qemu/launch', methods=['POST'])
def launch():
    if request.headers.get('authorization', None) != settings.LAUNCH_AUTH_HEADER:
        abort(403)
    if len(emulators) >= settings.EMULATOR_LIMIT:
        abort(503)
    uuid = uuid4()
    if '/' in request.form['platform'] or '/' in request.form['version']:
        abort(400)
    emu = Emulator(
        request.form['token'],
        request.form['platform'],
        request.form['version'],
        tz_offset=(int(request.form['tz_offset']) if 'tz_offset' in request.form else None),
        oauth=request.form.get('oauth', None)
    )
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
            logging.exception("failed to kill emulator")
            pass
        else:
            del emulators[emu]
        return jsonify(alive=False)


@app.route('/qemu/<emu>/kill', methods=['POST'])
def kill(emu):
    try:
        emu = UUID(emu)
    except ValueError:
        abort(404)
    if emu in emulators:
        try:
            emulators[emu].kill()
        except Exception:
            logging.exception("failed to kill")
        else:
            del emulators[emu]
    return jsonify(status='ok')


def proxy_ws(emu, attr, subprotocols=[]):
    server_ws = request.environ.get('wsgi.websocket', None)
    if server_ws is None:
        return "websocket endpoint", 400

    try:
        emulator = emulators[UUID(emu)]
    except ValueError:
        abort(404)
        return  # unreachable but makes IDE happy.
    target_url = "ws://localhost:%d/" % getattr(emulator, attr)
    try:
        client_ws = websocket.create_connection(target_url, subprotocols=subprotocols, sslopt={
            'ssl_version': ssl.PROTOCOL_TLSv1,
            'ca_certs': '%s/ca-cert.pem' % settings.SSL_ROOT,
            'cert_reqs': ssl.CERT_NONE,
        })
    except:
        logging.exception("connection to %s failed.", target_url)
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

app.app_protocol = lambda x: 'binary' if 'vnc' in x else None

@app.route('/qemu/<emu>/ws/phone')
def ws_phone(emu):
    return proxy_ws(emu, 'ws_port')

@app.route('/qemu/<emu>/ws/vnc')
def ws_vnc(emu):
    return proxy_ws(emu, 'vnc_ws_port', subprotocols=['binary'])


def _kill_idle_emulators():
    try:
        while True:
            try:
                logging.info("running idle killer for %d emulators", len(emulators))
                for key, emulator in emulators.items():
                    logging.debug("checking %s", key)
                    if now() - emulator.last_ping > 300:
                        logging.info("killing idle emulator %s", key)
                        emulator.kill()
                        del emulators[key]
                    else:
                        logging.debug("okay; last ping: %s", emulator.last_ping)
            except Exception:
                logging.exception('Failed to kill idle emulator')
            sys.stdout.flush()
            gevent.sleep(60)
    except Exception:
        logging.exception("IDLE EMULATOR WATCHDOG DIED. %d emulators were running.", len(emulators))
        raise

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

logging.info("Emulator limit: %d", settings.EMULATOR_LIMIT)

if __name__ == '__main__':
    app.debug = settings.DEBUG
    ssl_args = {}
    if settings.SSL_ROOT is not None:
        ssl_args = {
            'keyfile': '%s/server-key.pem' % settings.SSL_ROOT,
            'certfile': '%s/server-cert.pem' % settings.SSL_ROOT,
            'ca_certs': '%s/ca-cert.pem' % settings.SSL_ROOT,
            'ssl_version': ssl.PROTOCOL_TLSv1_2,
            'ciphers': 'EECDH+ECDSA+AESGCM EECDH+aRSA+AESGCM EECDH+ECDSA+SHA384 EECDH+ECDSA+SHA256 EECDH+aRSA+SHA384 EECDH+aRSA+SHA256 EECDH+aRSA+RC4 EECDH EDH+aRSA RC4 !aNULL !eNULL !LOW !3DES !MD5 !EXP !PSK !SRP !DSS !RC4',
        }
    server = pywsgi.WSGIServer(('', settings.PORT), app, handler_class=WebSocketHandler, **ssl_args)
    server.start()
    if settings.RUN_AS_USER is not None:
        drop_privileges(settings.RUN_AS_USER, settings.RUN_AS_USER)
    server.serve_forever()
