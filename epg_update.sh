#!/bin/bash
# Daily EPG refresh
curl -sL --max-time 300 "https://cdn.jsdelivr.net/gh/Some0ne11/EPGMalaysiaIPTV@main/epg.xml" \
  -o /home/hermes/mytv_playlist/epg.xml.new && \
  mv /home/hermes/mytv_playlist/epg.xml.new /home/hermes/mytv_playlist/epg.xml
