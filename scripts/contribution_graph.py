#!/usr/bin/env python3
"""Render the contribution calendar as an animated SVG for the README.

Fetches the last year of contributions via the GitHub GraphQL API and writes
assets/contribs-{light,dark}.svg. Each cell animates in with a per-column
delay, producing a left-to-right wave reveal when the profile loads. Pure
CSS — no JS — so it plays inside GitHub's camo image proxy.

Token comes from $GITHUB_TOKEN (Actions) or `gh auth token` (local).
"""
import json
import os
import subprocess
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(ROOT, "assets")
LOGIN = "ConnorXTan"

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2,
          "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

THEMES = {
    "light": {
        "ramp": ["#eef2f7", "#bfdbfe", "#60a5fa", "#2563eb", "#1e3a8a"],
        "text": "#57606a",
    },
    "dark": {
        "ramp": ["#161b22", "#1e3a8a", "#2563eb", "#60a5fa", "#93c5fd"],
        "text": "#8b949e",
    },
}

CELL, GAP = 11, 3
STEP = CELL + GAP
LEFT, TOP = 30, 20      # room for weekday / month labels
BOTTOM = 26             # room for total + legend
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]


def fetch_calendar():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        token = subprocess.run(["gh", "auth", "token"], capture_output=True,
                               text=True, check=True).stdout.strip()
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount contributionLevel weekday } }
          }
        }
      }
    }"""
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
        data=json.dumps({"query": query, "variables": {"login": LOGIN}}).encode(),
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        out = json.loads(resp.read().decode())
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    return out["data"]["user"]["contributionsCollection"]["contributionCalendar"]


def render(cal, theme):
    t = THEMES[theme]
    weeks = cal["weeks"]
    n_weeks = len(weeks)
    w = LEFT + n_weeks * STEP - GAP + 10
    h = TOP + 7 * STEP - GAP + BOTTOM
    wave_end_ms = n_weeks * 16 + 6 * 10 + 450  # last cell's delay + duration

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f"""<style>
.c {{
  opacity: 0;
  transform-box: fill-box;
  transform-origin: center;
  animation: rise .45s cubic-bezier(.22,.61,.36,1) both;
}}
.t {{
  opacity: 0;
  animation: fade .6s ease-out both;
  animation-delay: {wave_end_ms}ms;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  fill: {t["text"]};
}}
.lbl {{
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 9px;
  fill: {t["text"]};
}}
@keyframes rise {{
  from {{ opacity: 0; transform: translateY(8px) scale(.5); }}
  to   {{ opacity: 1; transform: none; }}
}}
@keyframes fade {{
  from {{ opacity: 0; }}
  to   {{ opacity: 1; }}
}}
@media (prefers-reduced-motion: reduce) {{
  .c, .t {{ animation: none; opacity: 1; }}
}}
</style>""",
    ]

    # month labels along the top (skip a label if it would crowd the previous)
    last_label_x = -100
    prev_month = None
    for wi, week in enumerate(weeks):
        month = int(week["contributionDays"][0]["date"][5:7])
        if month != prev_month:
            x = LEFT + wi * STEP
            if x - last_label_x >= 28:
                parts.append(f'<text class="lbl" x="{x}" y="12">{MONTHS[month - 1]}</text>')
                last_label_x = x
            prev_month = month

    # weekday labels
    for wd, label in ((1, "mon"), (3, "wed"), (5, "fri")):
        y = TOP + wd * STEP + CELL - 2
        parts.append(f'<text class="lbl" x="0" y="{y}">{label}</text>')

    # cells, wave delay left-to-right with a slight downward ripple
    for wi, week in enumerate(weeks):
        for day in week["contributionDays"]:
            x = LEFT + wi * STEP
            y = TOP + day["weekday"] * STEP
            fill = t["ramp"][LEVELS.get(day["contributionLevel"], 0)]
            delay = wi * 16 + day["weekday"] * 10
            parts.append(
                f'<rect class="c" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
                f'rx="2.5" fill="{fill}" style="animation-delay:{delay}ms"/>'
            )

    # total (bottom-left) and legend (bottom-right), fading in after the wave
    base_y = TOP + 7 * STEP - GAP + 17
    parts.append(
        f'<text class="t" x="{LEFT}" y="{base_y}">'
        f'{cal["totalContributions"]} contributions in the last year</text>'
    )
    legend_x = w - 10 - 5 * STEP - 60
    parts.append(f'<text class="t" x="{legend_x}" y="{base_y}">less</text>')
    for i, color in enumerate(t["ramp"]):
        parts.append(
            f'<rect class="c" x="{legend_x + 30 + i * STEP}" y="{base_y - 9}" '
            f'width="{CELL}" height="{CELL}" rx="2.5" fill="{color}" '
            f'style="animation-delay:{wave_end_ms}ms"/>'
        )
    parts.append(f'<text class="t" x="{legend_x + 30 + 5 * STEP + 4}" y="{base_y}">more</text>')

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main():
    cal = fetch_calendar()
    os.makedirs(ASSETS_DIR, exist_ok=True)
    for theme in THEMES:
        with open(os.path.join(ASSETS_DIR, f"contribs-{theme}.svg"), "w") as f:
            f.write(render(cal, theme))
    print(f"rendered {cal['totalContributions']} contributions")


if __name__ == "__main__":
    main()
