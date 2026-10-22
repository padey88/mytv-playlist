#!/bin/bash
# Daily EPG refresh — merges Some0ne11 (primary) + MIFNtechnology/StreamLiveTv EPG
# into one XMLTV file served at epg.kulnem.space/epg.xml
set -e
DIR=/home/hermes/mytv_playlist
UA="Mozilla/5.0"

curl -sL --max-time 300 -A "$UA" "https://cdn.jsdelivr.net/gh/Some0ne11/EPGMalaysiaIPTV@main/epg.xml" -o "$DIR/epg_a.xml"
curl -sL --max-time 300 -A "$UA" "https://raw.githubusercontent.com/MIFNtechnology/StreamLiveTv/main/epg.xml" -o "$DIR/epg_b.xml"

python3 - "$DIR" <<'PYEOF'
import re, sys
d = sys.argv[1]
a = open(f"{d}/epg_a.xml", encoding="utf-8", errors="ignore").read()
b = open(f"{d}/epg_b.xml", encoding="utf-8", errors="ignore").read()

def split(xml):
    chans = re.findall(r"<channel .*?</channel>", xml, re.S)
    progs = re.findall(r"<programme .*?</programme>", xml, re.S)
    return chans, progs

ca, pa = split(a)
cb, pb = split(b)
seen = set()
chans = []
for c in ca + cb:
    cid = re.search(r'id="([^"]+)"', c).group(1)
    if cid in seen: continue
    seen.add(cid); chans.append(c)
seenp = set()
progs = []
for p in pa + pb:
    key = (re.search(r'channel="([^"]+)"', p).group(1), re.search(r'start="([^"]+)"', p).group(1))
    if key in seenp: continue
    seenp.add(key); progs.append(p)

out = ('<?xml version="1.0" encoding="UTF-8"?>\n<tv>\n' +
       "\n".join(chans) + "\n" + "\n".join(progs) + "\n</tv>\n")
open(f"{d}/epg.xml", "w", encoding="utf-8").write(out)
print(f"merged EPG: {len(chans)} channels, {len(progs)} programmes")
PYEOF

rm -f "$DIR/epg_a.xml" "$DIR/epg_b.xml"
echo "EPG update done: $(stat -c%s $DIR/epg.xml) bytes"
