#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import threading

import xbmc
import xbmcaddon  # pylint: disable=import-error
ADDON = xbmcaddon.Addon('service.rabits.control-interceptor')

from urllib.request import Request, urlopen
from urllib.error import HTTPError
from http.server import BaseHTTPRequestHandler, HTTPServer

class ProxyHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        """Logging to xbmc log if debug is enabled"""
        if ADDON.getSettingBool('debug_enable'):
            xbmc.log("Control Interceptor: " + fmt % args, level=xbmc.LOGINFO)

    def do_GET(self):
        self.forward_request()

    def do_POST(self):
        # Intercept jsonrpc requests
        if self.path == '/jsonrpc':
            self.intercept_jsonrpc()
        else:
            self.forward_request()

    def do_PUT(self):
        self.forward_request()

    def do_DELETE(self):
        self.forward_request()

    def do_HEAD(self):
        self.forward_request()

    def intercept_jsonrpc(self):
        data = json.loads(self.get_data())
        if ADDON.getSettingBool('debug_enable'):
            xbmc.log("Control Interceptor: JSONRPC: %s" % (data,), level=xbmc.LOGINFO)

        # Stub the dangerous methods to process them separately
        method = data.get('method')
        if method in ('System.Suspend', 'System.Reboot', 'System.Shutdown', 'System.Hibernate', 'Application.Quit'):
            data['method'] = 'JSONRPC.Permission'

        # Replace the youtube plugin with youtube-dl sendtokodi
        if data.get('method') == 'Player.Open' and data.get('params', {}).get('item', {}).get('file', '').startswith('plugin://plugin.video.youtube/'):
            data['params']['item']['file'] = data['params']['item']['file'].replace('plugin://plugin.video.youtube/play/?video_id=', 'plugin://plugin.video.sendtokodi/?https://youtu.be/')

        resp = self.forward_request(json.dumps(data, separators=(',', ':')).encode())
        if resp != False:
            out_data = json.loads(resp)

            # Execute it only if auth was successfull
            if isinstance(out_data.get('result'), dict) and out_data.get('result', {}).get('ControlGUI'):
                if method in ('System.Suspend', 'System.Reboot', 'System.Shutdown', 'System.Hibernate', 'Application.Quit'):
                    os.system('/home/user/local/kodi_control/kodi_callback_trigger.sh')

    def get_data(self):
        length = self.headers.get('content-length')
        try:
            return self.rfile.read(int(length))
        except (TypeError, ValueError):
            pass

        return None

    def forward_request(self, data = None):
        if not hasattr(self.server, 'target_port'):
            self.update_target_port()
        url = 'http://{}:{}{}'.format('127.0.0.1', self.server.target_port, self.path)

        # Call the target service
        req = Request(url, method = self.command, headers = self.headers, data = data if data else self.get_data())
        req.remove_header('Host')
        if req.data:
            req.add_header('Content-Length', len(req.data))

        try:
            resp = urlopen(req, timeout=5)
            self.send_response(resp.status)
            for key, val in resp.headers.items():
                self.send_header(key, val)
            self.end_headers()
            data = resp.read()
            self.wfile.write(data)
            return data
        except HTTPError as e:
            self.send_response(e.code)
            for key, val in e.headers.items():
                self.send_header(key, val)
            self.end_headers()
            self.wfile.write(e.reason.encode())
        except URLError as e:
            xbmc.log("Kodi Control Interceptor request error: %s" % (e,), level=xbmc.LOGINFO)
            self.update_target_port()

        return False

    def update_target_port(self):
        data = json.loads(xbmc.executeJSONRPC('{"jsonrpc":"2.0","id":1,"method":"Settings.GetSettingValue","params":{"setting":"services.webserverport"}}'))
        self.server.target_port = data.get('result', {}).get('value')
        xbmc.log("Kodi Control Interceptor set target port to %s" % (self.server.target_port,), level=xbmc.LOGINFO)

if __name__ == '__main__':
    monitor = xbmc.Monitor()
    xbmc.log("Kodi Control Interceptor running...", level=xbmc.LOGINFO)

    server_address = ('0.0.0.0', ADDON.getSettingInt('listen_port'))
    httpd = HTTPServer(server_address, ProxyHTTPRequestHandler)
    thread = threading.Thread(None, httpd.serve_forever)
    thread.start()

    xbmc.log("Kodi Control Interceptor started", level=xbmc.LOGINFO)

    while not monitor.abortRequested():
        if monitor.waitForAbort(10):
            break

    httpd.shutdown()

    xbmc.log("Kodi Control Interceptor stopped", level=xbmc.LOGINFO)
