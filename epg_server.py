#!/usr/bin/env python3
"""Serves epg.xml (daily-downloaded from Some0ne11 EPG) on :8998."""
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
EPG = "/home/hermes/mytv_playlist/epg.xml"

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if not os.path.exists(EPG):
            self.send_response(404); self.end_headers(); return
        body = open(EPG,'rb').read()
        self.send_response(200)
        self.send_header("Content-Type","application/xml")
        self.send_header("Content-Length",str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*a): pass

HTTPServer(("0.0.0.0",8998),H).serve_forever()
