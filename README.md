# MYTV Mana-Mana Playlist Generator

Live m3u playlist for MYTV Mana-Mana (mana2.my) — 45 free Malaysian TV + radio channels.

The upstream signs each HLS URL with a ~30min expiry, so a static playlist dies quickly.
This service re-signs on every request via the public channel-play API.

## Endpoints
- `GET /` — full playlist (TV + radio), fresh tokens

## Setup (any Linux box)
    python3 mytv_server.py   # serves on :8999

Point TiviMate at http://<host>:8999/ and set auto-refresh <= 25 min.

## Channels
TV: TV1, TV2, TV AlHijrah, MySports, SUKAN+, Berita RTM, TV Okey, BERNAMA, USIM TV,
Siara TV, Selangor TV, TVIKIM, Borneo TV, Free Movies, Indonesia Channel, CNA,
Al Jazeera EN/AR, Euronews, Arirang, TaiwanPlus, NHK World, DW, RT International
Radio: Hot FM, Suria FM, Fly FM, Rakita FM, Manis FM, Molek FM, Best FM, Eight FM,
Kool FM, Ikim FM, Nasional FM, Traxx FM, Minnal FM, AI FM, Radio Klasik, Sabah FM,
Sabahv FM, Sarawak FM, Wai FM, Asyik FM, Bernama Radio

TVS excluded (Widevine DRM).
For personal use — streams belong to MYTV Broadcasting / RTM.
