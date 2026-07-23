#!/usr/bin/env python3
"""Refresh the live-stats block in README.md.

Pulls Monkeytype personal-best WPM and the Spotify now/last-played track,
then rewrites everything between the STATS markers. Missing secrets degrade
gracefully (that stat is skipped) so the workflow never hard-fails.

Env: MONKEYTYPE_APEKEY, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
     SPOTIFY_REFRESH_TOKEN
"""
import base64
import json
import os
import re
import sys
import urllib.parse
import urllib.request

README_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "README.md")


UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def http(url, headers=None, data=None, timeout=15):
    headers = dict(headers or {})
    headers.setdefault("User-Agent", UA)
    req = urllib.request.Request(url, headers=headers, data=data)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 204:
                return None
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {e.code}: {body}") from None


def monkeytype_wpm():
    key = os.environ.get("MONKEYTYPE_APEKEY")
    if not key:
        return None
    try:
        out = http(
            "https://api.monkeytype.com/users/personalBests?mode=words&mode2=10",
            headers={"Authorization": f"ApeKey {key}"},
        )
    except Exception as e:
        print(f"monkeytype: {e}", file=sys.stderr)
        return None

    # Defensively fish out every "wpm" value in the payload and take the best.
    wpms = []

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k == "wpm" and isinstance(v, (int, float)):
                    wpms.append(v)
                else:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)
    return round(max(wpms)) if wpms else None


def spotify_track():
    cid = os.environ.get("SPOTIFY_CLIENT_ID")
    secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    refresh = os.environ.get("SPOTIFY_REFRESH_TOKEN")
    if not (cid and secret and refresh):
        return None
    try:
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        tok = http(
            "https://accounts.spotify.com/api/token",
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data=urllib.parse.urlencode(
                {"grant_type": "refresh_token", "refresh_token": refresh}
            ).encode(),
        )
        auth = {"Authorization": f"Bearer {tok['access_token']}"}

        now = None
        try:
            now = http("https://api.spotify.com/v1/me/player/currently-playing", headers=auth)
        except Exception:
            pass
        if now and now.get("item"):
            item, verb = now["item"], "now playing"
        else:
            recent = http("https://api.spotify.com/v1/me/player/recently-played?limit=1", headers=auth)
            if not recent or not recent.get("items"):
                return None
            item, verb = recent["items"][0]["track"], "last played"

        images = item.get("album", {}).get("images", [])
        art = images[-1]["url"] if images else None  # smallest size
        return {
            "verb": verb,
            "name": item["name"],
            "artist": ", ".join(a["name"] for a in item["artists"]),
            "url": item["external_urls"]["spotify"],
            "art": art,
        }
    except Exception as e:
        print(f"spotify: {e}", file=sys.stderr)
        return None


def build_block(wpm, track_md):
    bits = []
    if wpm:
        bits.append(f"⌨️ **10-word pb:** {wpm} wpm")
    if track_md:
        bits.append(track_md)
    if not bits:
        return "⚙️ <sub>live stats warming up…</sub>"
    return " &nbsp;·&nbsp; ".join(bits)


def main():
    with open(README_PATH) as f:
        content = f.read()
    m = re.search(r"<!--STATS:START-->(.*?)<!--STATS:END-->", content, re.S)
    prev = m.group(1) if m else ""

    # a failed fetch keeps the previous value instead of erasing the stat
    wpm = monkeytype_wpm()
    if wpm is None:
        pm = re.search(r"\*\*10-word pb:\*\* (\d+) wpm", prev)
        wpm = int(pm.group(1)) if pm else None

    track = spotify_track()
    if track:
        art = f'<img src="{track["art"]}" height="16" alt=""/> ' if track["art"] else ""
        track_md = f'🎧 **{track["verb"]}:** {art}[{track["name"]} — {track["artist"]}]({track["url"]})'
    else:
        tm = re.search(r"(🎧 \*\*[^\n]+)", prev)
        track_md = tm.group(1).rstrip() if tm else None

    block = build_block(wpm, track_md)
    new = re.sub(
        r"(<!--STATS:START-->).*?(<!--STATS:END-->)",
        lambda m: m.group(1) + "\n" + block + "\n" + m.group(2),
        content,
        flags=re.S,
    )
    if new != content:
        with open(README_PATH, "w") as f:
            f.write(new)
        print("updated")
    else:
        print("no change")


if __name__ == "__main__":
    main()
