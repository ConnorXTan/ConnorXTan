#!/usr/bin/env python3
"""Connect Four engine for the profile README.

One shared board, played by anyone on GitHub. Moves arrive as issues titled
``c4|drop|<column>``; the connect-four workflow calls this script to apply
them, re-render the board SVGs, and rewrite the game section of README.md.

Usage:
  connect_four.py move --col N --user LOGIN   apply a move (prints result JSON)
  connect_four.py render                      re-render SVGs + README only
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(ROOT, "games", "connect4", "state.json")
README_PATH = os.path.join(ROOT, "README.md")
ASSETS_DIR = os.path.join(ROOT, "assets")

ROWS, COLS = 6, 7
OWNER = "ConnorXTan"
REPO = f"{OWNER}/{OWNER}"

RED, YELLOW = "R", "Y"
EMOJI = {RED: "\U0001F534", YELLOW: "\U0001F7E1"}
NAME = {RED: "red", YELLOW: "yellow"}


# ---------------------------------------------------------------- state

def new_game():
    return {
        "board": [[None] * COLS for _ in range(ROWS)],  # row 0 = top
        "turn": RED,
        "last_player": None,
        "last_col": None,
        "moves": [],
        "win_cells": [],
    }


def default_state():
    return {
        "game": new_game(),
        "stats": {"games": 0, "red_wins": 0, "yellow_wins": 0, "draws": 0},
        "last_result": None,
    }


def load_state():
    if not os.path.exists(STATE_PATH):
        return default_state()
    with open(STATE_PATH) as f:
        return json.load(f)


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


# ---------------------------------------------------------------- rules

def drop_row(board, col):
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] is None:
            return r
    return None


def find_win(board):
    for r in range(ROWS):
        for c in range(COLS):
            color = board[r][c]
            if color is None:
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                cells = [(r + i * dr, c + i * dc) for i in range(4)]
                if all(
                    0 <= rr < ROWS and 0 <= cc < COLS and board[rr][cc] == color
                    for rr, cc in cells
                ):
                    return color, cells
    return None, []


def board_full(board):
    return all(cell is not None for cell in board[0])


def apply_move(state, col, user):
    game = state["game"]
    if not 1 <= col <= COLS:
        return {"ok": False, "message": f"Column must be 1-{COLS}, got `{col}`. Pick a column from the board links!"}
    if game["last_player"] == user and user != OWNER:
        return {"ok": False, "message": f"You just moved, @{user} — give someone else a turn! (One move per person per turn.)"}
    c = col - 1
    r = drop_row(game["board"], c)
    if r is None:
        return {"ok": False, "message": f"Column {col} is full — pick another one!"}

    color = game["turn"]
    game["board"][r][c] = color
    game["turn"] = YELLOW if color == RED else RED
    game["last_player"] = user
    game["last_col"] = c
    game["moves"].append({"col": col, "color": color, "user": user})
    game["moves"] = game["moves"][-50:]

    winner, cells = find_win(game["board"])
    if winner:
        game["win_cells"] = [list(x) for x in cells]
        state["stats"]["games"] += 1
        state["stats"]["red_wins" if winner == RED else "yellow_wins"] += 1
        state["last_result"] = {"kind": "win", "color": winner, "user": user}
        msg = (
            f"{EMOJI[winner]} **@{user} wins it for {NAME[winner]}** with a connect four! "
            f"New game starting — the board is fresh."
        )
        finished = dict(game)
        state["game"] = new_game()
        state["game"]["moves"] = [{"col": col, "color": winner, "user": user, "won": True}]
        return {"ok": True, "message": msg, "finished_board": finished}
    if board_full(game["board"]):
        state["stats"]["games"] += 1
        state["stats"]["draws"] += 1
        state["last_result"] = {"kind": "draw", "color": None, "user": user}
        state["game"] = new_game()
        return {"ok": True, "message": "It's a draw — board full with no connect four. Fresh board is up!"}

    nxt = state["game"]["turn"]
    return {"ok": True, "message": f"{EMOJI[color]} Dropped in column {col}! {EMOJI[nxt]} {NAME[nxt].capitalize()} moves next."}


# ---------------------------------------------------------------- svg

THEMES = {
    "light": {
        "frame": "#2563eb", "frame_edge": "#1e40af", "hole": "#ffffff",
        "num": "#57606a", "red": "#ef4444", "red_hi": "#fca5a5",
        "yellow": "#eab308", "yellow_hi": "#fde047", "ring": "#16a34a",
        "marker": "#57606a",
    },
    "dark": {
        "frame": "#1e40af", "frame_edge": "#172554", "hole": "#0d1117",
        "num": "#8b949e", "red": "#dc2626", "red_hi": "#f87171",
        "yellow": "#ca8a04", "yellow_hi": "#facc15", "ring": "#22c55e",
        "marker": "#8b949e",
    },
}

CELL, PAD, TOP, NUM_H = 64, 18, 26, 34


def render_svg(game, theme):
    t = THEMES[theme]
    w = COLS * CELL + PAD * 2
    board_h = ROWS * CELL + PAD * 2
    h = TOP + board_h + NUM_H
    win = {tuple(c) for c in game.get("win_cells", [])}

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect x="0" y="{TOP}" width="{w}" height="{board_h}" rx="18" fill="{t["frame_edge"]}"/>',
        f'<rect x="0" y="{TOP}" width="{w}" height="{board_h - 6}" rx="18" fill="{t["frame"]}"/>',
    ]

    if game.get("last_col") is not None:
        cx = PAD + game["last_col"] * CELL + CELL // 2
        parts.append(
            f'<path d="M {cx - 9} 6 L {cx + 9} 6 L {cx} 20 Z" fill="{t["marker"]}"/>'
        )

    for r in range(ROWS):
        for c in range(COLS):
            cx = PAD + c * CELL + CELL // 2
            cy = TOP + PAD + r * CELL + CELL // 2 - 3
            color = game["board"][r][c]
            if color is None:
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="24" fill="{t["hole"]}"/>')
                continue
            fill = t["red"] if color == RED else t["yellow"]
            hi = t["red_hi"] if color == RED else t["yellow_hi"]
            parts.append(f'<circle cx="{cx}" cy="{cy}" r="24" fill="{fill}"/>')
            parts.append(f'<circle cx="{cx - 8}" cy="{cy - 9}" r="7" fill="{hi}" opacity="0.7"/>')
            if (r, c) in win:
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="27" fill="none" stroke="{t["ring"]}" stroke-width="4"/>')

    for c in range(COLS):
        cx = PAD + c * CELL + CELL // 2
        parts.append(
            f'<text x="{cx}" y="{TOP + board_h + 24}" text-anchor="middle" '
            f'font-family="ui-monospace, SFMono-Regular, Menlo, monospace" '
            f'font-size="17" fill="{t["num"]}">{c + 1}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------- readme

def issue_url(col):
    title = f"c4%7Cdrop%7C{col}"
    body = "press+create+and+the+board+will+update+in+~30+seconds."
    return f"https://github.com/{REPO}/issues/new?title={title}&body={body}"


def readme_section(state):
    game = state["game"]
    stats = state["stats"]
    turn = game["turn"]

    links = []
    for c in range(COLS):
        if drop_row(game["board"], c) is not None:
            links.append(f"[**{c + 1}**]({issue_url(c + 1)})")
        else:
            links.append(f"~~{c + 1}~~")
    link_row = " &nbsp; ".join(links)

    recent = []
    for m in reversed(game["moves"][-5:]):
        won = " — **winning move!** 🏆" if m.get("won") else ""
        recent.append(f"- {EMOJI[m['color']]} [@{m['user']}](https://github.com/{m['user']}) → column {m['col']}{won}")
    recent_md = "\n".join(recent) if recent else "*No moves yet this game — start it off!*"

    sub_bits = [
        f"🎮 game **{stats['games'] + 1}**",
        f"🔴 wins: **{stats['red_wins']}**",
        f"🟡 wins: **{stats['yellow_wins']}**",
        f"🤝 draws: **{stats['draws']}**",
    ]
    last = state.get("last_result")
    if last and last["kind"] == "win":
        sub_bits.append(f"last game: {EMOJI[last['color']]} won, clinched by [@{last['user']}](https://github.com/{last['user']}) 🏆")
    elif last and last["kind"] == "draw":
        sub_bits.append("last game: a draw 🤝")
    sub_line = " · ".join(sub_bits)

    seq = state.get("seq", 0)
    return f"""
{EMOJI[turn]} **{NAME[turn]} moves next** — click a column number and press *create* to drop a disc.

<div align="center">

<picture>
<source media="(prefers-color-scheme: dark)" srcset="assets/board-dark.svg?v={seq}">
<img alt="Connect Four board" src="assets/board-light.svg?v={seq}" width="420">
</picture>

⬇️&nbsp;&nbsp;{link_row}

</div>

**Recent moves**

{recent_md}

<sub>{sub_line}</sub>
"""


def rewrite_readme(state):
    with open(README_PATH) as f:
        content = f.read()
    section = readme_section(state)
    new = re.sub(
        r"(<!--C4:START-->).*?(<!--C4:END-->)",
        lambda m: m.group(1) + "\n" + section + "\n" + m.group(2),
        content,
        flags=re.S,
    )
    if new != content:
        with open(README_PATH, "w") as f:
            f.write(new)


def render_all(state, finished_board=None):
    # If a game just ended, show the finished board (with the winning ring)
    # rather than the freshly reset empty one.
    game = finished_board or state["game"]
    os.makedirs(ASSETS_DIR, exist_ok=True)
    for theme in THEMES:
        with open(os.path.join(ASSETS_DIR, f"board-{theme}.svg"), "w") as f:
            f.write(render_svg(game, theme))
    rewrite_readme(state)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    mv = sub.add_parser("move")
    mv.add_argument("--col", type=int, required=True)
    mv.add_argument("--user", required=True)
    sub.add_parser("render")
    args = ap.parse_args()

    state = load_state()
    if args.cmd == "render":
        save_state(state)
        render_all(state)
        print(json.dumps({"ok": True, "message": "rendered"}))
        return

    state["seq"] = state.get("seq", 0) + 1
    result = apply_move(state, args.col, args.user)
    if result["ok"]:
        save_state(state)
        render_all(state, finished_board=result.pop("finished_board", None))
    print(json.dumps(result))
    sys.exit(0 if result["ok"] else 78)  # 78 = invalid move (workflow comments, no commit)


if __name__ == "__main__":
    main()
