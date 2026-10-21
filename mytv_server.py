#!/usr/bin/env python3
"""MYTV Mana-Mana playlist generator - mints fresh signed HLS URLs on every request.
Auth: ?token=<MYTV_TOKEN> (because TiviMate cannot send HTTP basic auth).

v2 (2026-10-21):
- TV channels: direct signed CDN URLs (TiviMate handles these fine).
- Radio channels: PROXIED through this server. Reason: the radio HLS variant is a
  RELATIVE "chunks.m3u8" and the .aac SEGMENTS require the ?md5&expires query that
  TiviMate does not propagate to relative segment URLs -> 403 -> radio dead.
  The proxy rewrites every layer (master/chunks/segments) so the token is always present.
"""
import json, os, re, time, urllib.request, urllib.parse, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

API = "https://co3y6iwoio.tenbytecdn.com/api/v1"
DEVICE = "tivimate-mytv-kulnem"
TOKEN = os.environ.get("MYTV_TOKEN", "")
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
            entries.append({"name": ch["name"], "num": ch["channelNumber"],
                            "type": ch["channelType"], "logo": ch.get("logoUrl") or "",
                            "hls": d["data"]["playbackUrls"]["hls"],
                            "id": ch["id"]})
        except Exception as e:
            print("skip", ch["name"], e, flush=True)
    return entries

def get_entries():
    with _lock:
        if time.time() - _cache["ts"] > CACHE_TTL or not _cache["data"]:
            try:
                _cache["data"] = build_entries()
                _cache["ts"] = time.time()
            except Exception:
                if not _cache["data"]:
                    raise
        return _cache["data"]

def mint(channel_id):
    """Mint a fresh signed HLS URL for a channel (used by the radio proxy)."""
    d = _post("/public/streaming/channel-play",
              {"channelId": channel_id, "deviceId": DEVICE, "platform": "web"})
    return d["data"]["playbackUrls"]["hls"]

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

# --- siaranMy (aliahk2024 fork) tonton-family channels, added on user request 2026-10-21 ---
# Streams point at tonton SSAI/Fastly hosts that were NXDOMAIN from the datacenter at
# test time — may still resolve from a Malaysian residential IP.
SIARMY = [
    (103, "TV3",           "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/channels/Tv3/index.m3u8",
     "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/logo/Tv3.png"),
    (105, "8TV",           "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/channels/8tv/index.m3u8",
     "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/logo/8tv.png"),
    (107, "TV9",           "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/channels/Tv9/index.m3u8",
     "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/logo/Tv9.png"),
    (109, "DidikTV KPM",   "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/channels/DidikTvKPM/index.m3u8",
     "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/logo/DidikTv.png"),
    (111, "Drama Sangat",  "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/channels/DramaSangat/index.m3u8",
     "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/logo/DramaSangat.png"),
]

GROUP = lambda e: ("Radio" if e["type"] == "audio" else "Live TV")

def render_m3u(base):
    """base = scheme://host of THIS server (as the client addressed it), e.g. https://mytv.kulnem.space"""
    lines = ['#EXTM3U url-tvg="https://epg.kulnem.space/epg.xml"']
    for e in get_entries():
        lines.append(f'#EXTINF:-1 tvg-chno="{e["num"]}" tvg-logo="{e["logo"]}" '
                     f'group-title="{GROUP(e)}",{e["name"]}')
        if e["type"] == "audio":
            slug = slugify(e["name"])
            lines.append(f"{base}/radio-proxy/{slug}?token={TOKEN}")
        else:
            lines.append(e["hls"])
    for num, name, url, logo in SIARMY:
        lines.append(f'#EXTINF:-1 tvg-chno="{num}" tvg-logo="{logo}" '
                     f'group-title="Live TV",{name}')
        lines.append(url)
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------- radio proxy
_radio_lock = threading.Lock()
_radio_map = {}  # slug -> {"id":..., "url": signed url, "ts": mint time}
RADIO_TTL = 15 * 60

def radio_signed(slug):
    """Get (or refresh) the signed upstream URL for a radio slug."""
    with _radio_lock:
        ent = _radio_map.get(slug)
        if not ent or time.time() - ent["ts"] > RADIO_TTL:
            chans = {slugify(c["name"]): c["id"] for c in _get_channels()}
            if slug not in chans:
                raise KeyError("unknown radio " + slug)
            url = mint(chans[slug])
            ent = {"id": chans[slug], "url": url, "ts": time.time()}
            _radio_map[slug] = ent
        return ent["url"]

def _upstream(url):
    req = urllib.request.Request(url, headers={"Origin": "https://mana2.my",
                                               "User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(req, timeout=10).read()

def radio_master(slug, base):
    """Rewrite the upstream master so chunks.m3u8 points back at our proxy with the query intact."""
    up = radio_signed(slug)
    # split off the query (md5/expires) to re-attach later
    parsed = urllib.parse.urlsplit(up)
    q = parsed.query
    body = _upstream(up).decode()
    slug_q = urllib.parse.quote(q)
    out = []
    for line in body.splitlines():
        if line and not line.startswith("#") and "m3u8" in line:
            line = f"{base}/radio-proxy/{slug}/chunks.m3u8?uq={slug_q}"
        out.append(line)
    return "\n".join(out) + "\n"

def radio_chunks(slug, uq):
    """Fetch upstream chunks.m3u8 (carrying the md5/expires query) and rewrite .aac segments
    to absolute upstream URLs WITH the same query, so any player gets a token on every segment."""
    up = radio_signed(slug)
    parsed = urllib.parse.urlsplit(up)
    base_dir = up.rsplit("/", 1)[0]  # .../radio/hotfm
    chunks_url = f"{base_dir}/chunks.m3u8?{uq}"
    body = _upstream(chunks_url).decode()
    out = []
    for line in body.splitlines():
        if line and not line.startswith("#"):
            line = f"{base_dir}/{line}?{uq}"  # segment with token -> direct CDN, playable
        out.append(line)
    return "\n".join(out) + "\n"

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="text/plain"):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        if TOKEN and params.get("token", [None])[0] != TOKEN and not parsed.path.startswith("/radio-proxy/"):
            self._send(401, "unauthorized")
            return
        base = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme else \
               f"http://{self.headers.get('Host', '192.168.100.230:8999')}"
        base = f"http://{self.headers.get('Host', '192.168.100.230:8999')}"
        path = parsed.path
        try:
            if path.startswith("/radio-proxy/"):
                parts = [p for p in path.split("/") if p]
                # /radio-proxy/<slug>[/chunks.m3u8]
                slug = parts[1] if len(parts) > 1 else ""
                if len(parts) >= 3 and parts[2] == "chunks.m3u8":
                    uq = params.get("uq", [""])[0]
                    if not uq:  # player hit chunks directly without query — mint fresh
                        u = radio_signed(slug)
                        uq = urllib.parse.urlsplit(u).query
                    self._send(200, radio_chunks(slug, uq), "audio/x-mpegurl")
                else:
                    self._send(200, radio_master(slug, base), "audio/x-mpegurl")
            else:
                self._send(200, render_m3u(base), "audio/x-mpegurl")
        except Exception as e:
            self._send(502, str(e))
    def log_message(self, *a): pass

if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("MYTV_TOKEN env var required")
    print("serving on :8999 with token auth + radio proxy", flush=True)
    HTTPServer(("0.0.0.0", 8999), H).serve_forever()
