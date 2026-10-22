#!/usr/bin/env python3
"""MYTV playlist generator v3.
- mana2.my RTM/international/radio channels (dynamic signed HLS, radio proxied)
- tonton-family + extra MY channels auto-synced from MIFNtechnology/StreamLiveTv
  (Astro clearkey DASH) — upstream m3u8 re-parsed on every cache cycle, so URL or
  clearkey changes upstream flow through automatically
- EPG: tvg-id mapping to Some0ne11 EPG ids for guide data on all channels
Auth: ?token=<MYTV_TOKEN> (TiviMate cannot send HTTP basic auth)."""
import json, os, re, time, urllib.request, urllib.parse, threading
from http.server import HTTPServer, BaseHTTPRequestHandler

API = "https://co3y6iwoio.tenbytecdn.com/api/v1"
DEVICE = "tivimate-mytv-kulnem"
TOKEN = os.environ.get("MYTV_TOKEN", "")
CACHE_TTL = 20 * 60  # re-sign mana2 + re-sync upstream repo every 20 min

SLTV_URL = "https://raw.githubusercontent.com/MIFNtechnology/StreamLiveTv/main/myIPtv.m3u8"

# Channels we take from StreamLiveTv: (upstream name, our label, chno, EPG id)
SLTV_MAP = [
    ("TV3",            "TV3",             103, "TV3"),
    ("8TV",            "8TV",             105, "8TV"),
    ("TV9",            "TV9",             107, "TV9"),
    ("DidikTv KPM",    "DidikTV KPM",     109, "DidikTVKPM"),
    ("BERNAMA",        "Bernama TV",      115, "BernamaTV"),
    ("TVS",            "TVS",             117, "TVSarawak"),
    ("CartoonNetwork", "Cartoon Network", 119, "CartoonNetwork"),
    ("Dunia Sinema",   "Dunia Sinema",    121, "DuniaSinema"),
]
# Drama Sangat is not in StreamLiveTv; static fork link (tonton Fastly)
DRAMA_SANGAT = ("Drama Sangat", 111, "DramaSangat",
                "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/channels/DramaSangat/index.m3u8",
                "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/logo/DramaSangat.png")
# Astro Awani is not in mana2 or StreamLiveTv-DRM; static fork link (verified live)
ASTRO_AWANI = ("Astro Awani", 113, "AstroAwaniHD",
               "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/channels/AstroAwani/index.m3u8",
               "https://raw.githubusercontent.com/aliahk2024/siaranMy/main/logo/AstroAwani.png")
STATIC_TV = [DRAMA_SANGAT, ASTRO_AWANI]

# mana2 channel name -> Some0ne11 EPG id (None = no EPG exists; omit attr)
EPG_MAP = {
    "TV1": "TV1", "TV2": "TV2", "TVS": "TVSarawak", "TV ALHIJRAH": "AlHijrah",
    "BERNAMA": "BernamaTV", "BERITA RTM": "BeritaRTM", "SUKAN+": "SukanRTM",
    "TV OKEY": "Okey",
    "CNA": "CNA", "AL JAZEERA ENGLISH HD": "AlJazeera", "EURONEWS": "Euronews",
    "NHK WORLD": "NHKWorldJapan", "DW": "DW",
    "FREE MOVIES": "FreeMovies", "ARIRANG": "Arirang.id",
    "TVIKIM": None,  # placeholder for future EPG sources
}

_lock = threading.Lock()
_cache = {"ts": 0, "data": [], "sltv": []}

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
                            "hls": d["data"]["playbackUrls"]["hls"], "id": ch["id"]})
        except Exception as e:
            print("skip", ch["name"], e, flush=True)
    return entries

def fetch_sltv():
    """Parse StreamLiveTv's m3u8 -> list of {name, logo, props, url}. Returns None on failure
    so the last good copy is kept."""
    try:
        req = urllib.request.Request(SLTV_URL, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=15).read().decode()
    except Exception as e:
        print("sltv sync failed:", e, flush=True)
        return None
    entries, cur = [], None
    for l in text.splitlines():
        if l.startswith("#EXTINF"):
            name = re.search(r",(.*)$", l)
            logo = re.search(r'tvg-logo="([^"]*)"', l)
            cur = {"name": name.group(1).strip() if name else "",
                   "logo": logo.group(1) if logo else "", "props": [], "url": ""}
        elif cur is not None and l.startswith("#"):
            # normalize upstream typos like "org.w3 .clearkey"
            cur["props"].append(re.sub(r"org\.w3\s+\.clearkey", "org.w3.clearkey", l))
        elif cur is not None and l.strip():
            cur["url"] = l.strip()
            entries.append(cur); cur = None
    return entries

def get_entries():
    with _lock:
        if time.time() - _cache["ts"] > CACHE_TTL or not _cache["data"]:
            try:
                _cache["data"] = build_entries()
                sltv = fetch_sltv()
                if sltv is not None:
                    _cache["sltv"] = sltv
                _cache["ts"] = time.time()
                print(f"sync: {len(_cache['data'])} mana2 + {len(_cache['sltv'])} sltv", flush=True)
            except Exception:
                if not _cache["data"]:
                    raise
        return _cache["data"], _cache["sltv"]

def mint(channel_id):
    d = _post("/public/streaming/channel-play",
              {"channelId": channel_id, "deviceId": DEVICE, "platform": "web"})
    return d["data"]["playbackUrls"]["hls"]

def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")

GROUP = lambda e: ("Radio" if e["type"] == "audio" else "Live TV")

def render_m3u(base):
    entries, sltv = get_entries()
    sltv_by_name = {e["name"]: e for e in sltv}
    lines = ['#EXTM3U url-tvg="https://epg.kulnem.space/epg.xml"']

    # mana2 channels (skip TVS — replaced by the Astro clearkey version below)
    norm_map = {re.sub(r"[^a-z0-9]", "", k.lower()): v for k, v in EPG_MAP.items()}
    for e in entries:
        if e["name"] in ("TVS", "BERNAMA"):
            continue
        tvg_id = norm_map.get(re.sub(r"[^a-z0-9]", "", e["name"].lower()))
        idattr = f' tvg-id="{tvg_id}"' if tvg_id else ""
        lines.append(f'#EXTINF:-1{idattr} tvg-chno="{e["num"]}" tvg-logo="{e["logo"]}" '
                     f'group-title="{GROUP(e)}",{e["name"]}')
        if e["type"] == "audio":
            lines.append(f"{base}/radio-proxy/{slugify(e['name'])}?token={TOKEN}")
        else:
            lines.append(e["hls"])

    # StreamLiveTv clearkey channels (auto-synced each cache cycle)
    for up_name, label, chno, epg_id in SLTV_MAP:
        ent = sltv_by_name.get(up_name)
        if not ent or not ent["url"]:
            print("sltv missing:", up_name, flush=True)
            continue
        lines.append(f'#EXTINF:-1 tvg-id="{epg_id}" tvg-chno="{chno}" tvg-logo="{ent["logo"]}" '
                     f'group-title="Live TV",{label}')
        lines.extend(ent["props"])  # KODIPROP clearkey + EXTVLCOPT user-agent
        lines.append(ent["url"])

    # Static extras (Drama Sangat, Astro Awani)
    for name, chno, epg_id, url, logo in STATIC_TV:
        lines.append(f'#EXTINF:-1 tvg-id="{epg_id}" tvg-chno="{chno}" tvg-logo="{logo}" '
                     f'group-title="Live TV",{name}')
        lines.append(url)
    return "\n".join(lines) + "\n"

# ---------------------------------------------------------------- radio proxy
_radio_lock = threading.Lock()
_radio_map = {}  # slug -> {"id":..., "url":..., "ts":...}
RADIO_TTL = 15 * 60

def radio_signed(slug):
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
    up = radio_signed(slug)
    q = urllib.parse.urlsplit(up).query
    body = _upstream(up).decode()
    slug_q = urllib.parse.quote(q)
    out = []
    for line in body.splitlines():
        if line and not line.startswith("#") and "m3u8" in line:
            line = f"{base}/radio-proxy/{slug}/chunks.m3u8?uq={slug_q}"
        out.append(line)
    return "\n".join(out) + "\n"

def radio_chunks(slug, uq):
    up = radio_signed(slug)
    base_dir = up.rsplit("/", 1)[0]
    chunks_url = f"{base_dir}/chunks.m3u8?{uq}"
    body = _upstream(chunks_url).decode()
    out = []
    for line in body.splitlines():
        if line and not line.startswith("#"):
            line = f"{base_dir}/{line}?{uq}"
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
        base = f"http://{self.headers.get('Host', '192.168.100.230:8999')}"
        path = parsed.path
        try:
            if path.startswith("/radio-proxy/"):
                parts = [p for p in path.split("/") if p]
                slug = parts[1] if len(parts) > 1 else ""
                if len(parts) >= 3 and parts[2] == "chunks.m3u8":
                    uq = params.get("uq", [""])[0]
                    if not uq:
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
    print("serving on :8999 — token auth, radio proxy, StreamLiveTv auto-sync", flush=True)
    HTTPServer(("0.0.0.0", 8999), H).serve_forever()
