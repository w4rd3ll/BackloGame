"""Public-library Steam relay. No Steam credentials are returned to clients."""
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
import urllib.parse

from library_sync import fetch_steam, profile_name

CACHE = OrderedDict()
LOCK = threading.Lock()
UPSTREAM = threading.BoundedSemaphore(2)
DAILY = {'day':0,'count':0}
KEY = (Path(os.environ.get('CREDENTIALS_DIRECTORY','/etc/backlogame'))/'steam_api_key').read_text().strip()


def library(profile):
    name = profile_name(profile,'steam')
    if not KEY:
        raise ValueError('Steam relay is not configured')
    now = time.time()
    with LOCK:
        cached = CACHE.get(name)
        if cached and now-cached[0]<600:
            CACHE.move_to_end(name)
            return cached[1]
    if not UPSTREAM.acquire(blocking=False):
        raise ValueError('Steam relay is busy. Try again shortly.')
    try:
        with LOCK:
            day=int(now//86400)
            if DAILY['day']!=day:DAILY.update(day=day,count=0)
            if DAILY['count']>=5000:raise ValueError('Daily request limit reached. Try again tomorrow.')
            DAILY['count']+=1
        result=fetch_steam(name,KEY)
        with LOCK:
            CACHE[name]=(time.time(),result)
            CACHE.move_to_end(name)
            while len(CACHE)>32:CACHE.popitem(last=False)
        return result
    finally:UPSTREAM.release()


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,data,status=200):
        raw=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        parts=urllib.parse.urlsplit(self.path)
        if len(self.path)>1024:return self.reply({'error':'Request too long'},414)
        if parts.path=='/health':return self.reply({'app':'backlogame-steam-relay','configured':bool(KEY)},200 if KEY else 503)
        if parts.path!='/v1/steam/library':return self.reply({'error':'Not found'},404)
        args=urllib.parse.parse_qs(parts.query)
        if set(args)!={'profile'} or len(args['profile'])!=1:return self.reply({'error':'Provide one Steam profile'},400)
        try:return self.reply({'games':library(args['profile'][0])})
        except ValueError as exc:return self.reply({'error':str(exc)},503 if not KEY else 400)
        except Exception:return self.reply({'error':'Steam is temporarily unavailable'},502)


if __name__=='__main__':
    ThreadingHTTPServer(('127.0.0.1',8787),Handler).serve_forever()
