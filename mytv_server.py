
#!/usr/bin/env python3
"""MYTV Mana-Mana playlist generator - mints fresh signed HLS URLs on every request."""
import json, time, urllib.request, threading

API = "https://co3y6iwoio.tenbytecdn.com/api/v1"
DEVICE = "tivimate-mytv-kulnem"
CACHE_TTL = 20 * 60  # re-sign every 20 min (tokens last 30)

_lock = threading.Lock()
_cache = {"ts": 0, "data": []}

def _post(path, body):
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Origin": "https://mana2.my",
                 "Referer": "https://mana2.my/", "User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())

def _get_channels():
    req = urllib.request.Request(API + "/channels",
        headers={"Origin": "https://mana2.my", "Referer": "https://mana2.my/"})
    return json.loads(urllib.request.urlopen(req, timeout=10).read())["data"]

def build_entries():
    chans = _get_channels()
    entries = []
    for ch in chans:
        try:
            d = _post("/public/streaming/channel-play",
                      {"channelId": ch["id"], "deviceId": DEVICE, "platform": "web"})
            if not d.get("success") or ch.get("drmEnabled"):
                continue
            hls = d["data"]["playbackUrls"]["hls"]
            entries.append({"name": ch["name"], "num": ch["channelNumber"],
                            "type": ch["channelType"], "logo": ch.get("logoUrl") or "", "hls": hls})
        except Exception as e:
            print("skip", ch["name"], e)
    return entries

def get_entries():
    with _lock:
        if time.time() - _cache["ts"] > CACHE_TTL or not _cache["data"]:
            try:
                _cache["data"] = build_entries()
                _cache["ts"] = time.time()
            except Exception as e:
                if not _cache["data"]:
                    raise
        return _cache["data"]

GROUP = lambda e: ("Radio MYTV" if e["type"] == "audio" else
                   "MYTV Malaysia" if e["num"] < 300 else "MYTV International")

def render_m3u():
    lines = ['#EXTM3U url-tvg="https://epg.kulnem.space/epg.xml"']
    for e in get_entries():
        lines.append(f'#EXTINF:-1 tvg-chno="{e["num"]}" tvg-logo="{e["logo"]}" '
                     f'group-title="{GROUP(e)}",{e["name"]}')
        lines.append(e["hls"])
    return "\n".join(lines) + "\n"

if __name__ == "__main__":
    from http.server import HTTPServer, BaseHTTPRequestHandler
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                body = render_m3u().encode()
                self.send_response(200)
                self.send_header("Content-Type", "audio/x-mpegurl")
                self.send_header("Content-Disposition", 'inline; filename="playlist.m3u"')
                self.end_headers()
                self.wfile.write(body)
            except Exception as e:
                self.send_response(502); self.end_headers(); self.wfile.write(str(e).encode())
        def log_message(self, *a): pass
    print("serving on :8999")
    HTTPServer(("0.0.0.0", 8999), H).serve_forever()
