#!/usr/bin/env python3
"""One-time local helper: mint the Spotify refresh token for the stats workflow.

Prereq (one-time, ~5 min):
  1. https://developer.spotify.com/dashboard → Create app
  2. Redirect URI: http://127.0.0.1:8888/callback   (Web API checked)
  3. Copy the app's Client ID and Client Secret

Run:  python3 scripts/spotify_refresh_token.py CLIENT_ID CLIENT_SECRET

Opens your browser to authorize, catches the redirect on a local server,
exchanges the code, and prints the refresh token. Store all three values as
repo secrets: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN.
"""
import base64
import json
import sys
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

REDIRECT = "http://127.0.0.1:8888/callback"
SCOPES = "user-read-currently-playing user-read-recently-played"


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: spotify_refresh_token.py CLIENT_ID CLIENT_SECRET")
    cid, secret = sys.argv[1], sys.argv[2]

    auth_url = "https://accounts.spotify.com/authorize?" + urllib.parse.urlencode(
        {"client_id": cid, "response_type": "code", "redirect_uri": REDIRECT, "scope": SCOPES}
    )
    print("Opening browser for Spotify authorization…")
    webbrowser.open(auth_url)

    code_holder = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code_holder["code"] = qs.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Done — you can close this tab.</h2>")

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 8888), Handler)
    print("Waiting for the redirect on http://127.0.0.1:8888 …")
    while "code" not in code_holder:
        server.handle_request()
    server.server_close()

    if not code_holder["code"]:
        sys.exit("Authorization was denied or no code returned.")

    basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
    req = urllib.request.Request(
        "https://accounts.spotify.com/api/token",
        headers={"Authorization": f"Basic {basic}",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(
            {"grant_type": "authorization_code", "code": code_holder["code"],
             "redirect_uri": REDIRECT}
        ).encode(),
    )
    with urllib.request.urlopen(req) as resp:
        tokens = json.loads(resp.read().decode())

    print("\nSPOTIFY_REFRESH_TOKEN:\n")
    print(tokens["refresh_token"])
    print("\nStore it with:  gh secret set SPOTIFY_REFRESH_TOKEN")


if __name__ == "__main__":
    main()
