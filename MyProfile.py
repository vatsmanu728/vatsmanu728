#!/usr/bin/env python3
"""
MyProfile.py

Regenerates dark_mode.svg and light_mode.svg from scratch on every run.
Don't hand-edit the SVG files -- edit the CONFIG block below instead and re-run 
(or just push; the GitHub Action re-runs this daily).

Every visible field/line gets a *sequential* y position computed at render time. 
There's no fixed slot reserved for hidden fields, so turning a field off (or leaving its value empty) 
simply closes the gap -- the next visible line moves up to take its place. 
A whole section (its header + surrounding blank line included) disappears the same way 
if none of its fields are visible.
"""

import os
import re
import sys
import textwrap
import datetime as dt
from pathlib import Path

import requests

ROOT = Path(__file__).parent
DRY_RUN = os.environ.get("DRY_RUN") == "1"     # use fake stats, skip API calls

# =============================================================================
# CONFIG -- edit this block for routine updates. 
# Nothing below the "GENERATION LOGIC" divider should need to change for normal edits.
# =============================================================================

GITHUB_USERNAME = "vatsmanu728"              # used for API calls
DISPLAY_NAME    = "< VATS MANU >"                # shown in the "name ------" header
BIRTHDATE       = "2002-03-31"               # YYYY-MM-DD -> powers "Uptime"

# Each section is a dict with 
# an optional "header" (None = no header line, just fields) 
# and a list of (label, value, show) tuples.
#
#   - value=None on a GitHub-Stats field means "compute it automatically".
#
#   - show=False hides the line without deleting it -- handy for fields you'll fill in later, 
#     or stats you don't want to show yet (e.g. a "0" you're not proud of showing off just yet).
#   
#   - A section with zero visible fields is skipped entirely, header, spacing and all.
#   - Long values wrap automatically onto an indented continuation line

SECTIONS = [
    {
        "header": None,
        "fields": [
                  ("Uptime", None, True),       # None = auto-computed from BIRTHDATE
                  ("Host", "DEI Technologies Ltd.", True),
                  ("Kernel", "Applied ML, AI Automation & LLMs, Data Science", True),
        ],
    },
    {
        "header": None,
        "fields": [
                  ("OS", "Android 14, Windows 8/10/11, Mac OS, Linux", True),
                  ("IDE", "VSCode 1.96.0, JetBrains PyCharm, Android Studio, "
                     "Copilot, Cursor, Antigravity", True),
        ],
    },
    {
        "header": None,
        "fields": [
                  ("Languages.Programming", "Python, C++, Bash, TypeScript, JavaScript, PostgreSQL, PL/pgSQL", True),  # fill more later
                  ("Languages.Computer", "JSON, CSV, HTML5, CSS3, XML, YAML, TOML, Markdown", True),            # fill more later
                  ("Languages.Real", "English, Hindi", True),
        ],
    },
    {
        "header": None,
        "fields": [
                  ("Hobbies.Software", "", False),           # fill in later
                  ("Hobbies.Hardware", "", False),           # fill in later
        ],
    },
    {
        "header": "Contact",
        "fields": [
                  ("Email.Personal", "vatsmanu728@gmail.com", False),
                  ("Email.Personal", "", False),
                  ("Email.Work", "vatsmanu728@gmail.com", True),  # fill in later
                  ("LinkedIn", "Mayank-Vats", True),
                  ("Whatsapp", "+91 70565 97805", True),
        ],
    },
    {
        "header": "GitHub Stats",
        "fields": [
            # value=None -> filled in by fetch_github_stats() below
                  ("Repos", None, True),
                  ("Commits", None, True),
                  ("Stars", None, False),                # hidden for now -- 0
                  ("Followers", None, False),            # hidden for now -- 0
                  ("Lines of Code", None, True),
        ],
    },
]

# =============================================================================
# GENERATION LOGIC
# =============================================================================

API = "https://api.github.com/graphql"
TOKEN = os.environ.get("GH_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}

CACHE_FILE = ROOT / "cache.txt"
ARCHIVE_FILE = ROOT / "repository_archive.txt"

VALUE_WRAP_WIDTH = 46   # chars per value line before wrapping
LABEL_COL = 30          # column where values start (after dots)


def gh_graphql(query, variables=None):
    r = requests.post(API, json={"query": query, "variables": variables or {}},
                       headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


def compute_uptime(birthdate_str, as_of=None):
    as_of = as_of or dt.date.today()
    y, m, d = map(int, birthdate_str.split("-"))
    birth = dt.date(y, m, d)
    years = as_of.year - birth.year
    months = as_of.month - birth.month
    days = as_of.day - birth.day
    if days < 0:
        months -= 1
        prev_month_end = as_of.replace(day=1) - dt.timedelta(days=1)
        days += prev_month_end.day
    if months < 0:
        years -= 1
        months += 12
    return f"{years} years, {months} months, {days} days"


# ---- cache helpers (per-repo commit count + cumulative additions/deletions)

def load_cache(path):
    cache = {}
    if path.exists():
        for line in path.read_text().splitlines():
            parts = line.split("\t")
            if len(parts) == 4:
                name, commits, add, dele = parts
                cache[name] = (int(commits), int(add), int(dele))
    return cache


def save_cache(path, cache):
    lines = [f"{name}\t{c}\t{a}\t{d}" for name, (c, a, d) in cache.items()]
    path.write_text("\n".join(lines) + ("\n" if lines else ""))


def fetch_repo_loc(owner, repo_name, user_id, known_count, known_add, known_del):
    # Walk commit history authored by user_id on the default branch.
    # Skips straight to 'no new commits' if the total count hasn't moved
    # since the last run -- this is what keeps daily runs fast.
    
    q = """
    query($owner:String!, $name:String!, $cursor:String) {
      repository(owner:$owner, name:$name) {
        defaultBranchRef {
          target { ... on Commit {
            history(first: 100, after: $cursor) {
              totalCount
              pageInfo { hasNextPage endCursor }
              nodes { additions deletions author { user { id } } }
            }
          }}
        }
      }
    }"""
    cursor = None
    total_count = None
    add_sum, del_sum, seen = 0, 0, 0
    while True:
        data = gh_graphql(q, {"owner": owner, "name": repo_name, "cursor": cursor})
        ref = data["repository"]["defaultBranchRef"]
        if not ref:
            return 0, 0, 0
        hist = ref["target"]["history"]
        if total_count is None:
            total_count = hist["totalCount"]
            if total_count == known_count:
                return known_count, known_add, known_del       # nothing new
        for node in hist["nodes"]:
            seen += 1
            author = node.get("author") or {}
            u = author.get("user") or {}
            if u.get("id") == user_id:
                add_sum += node["additions"]
                del_sum += node["deletions"]
        if not hist["pageInfo"]["hasNextPage"]:
            break
        cursor = hist["pageInfo"]["endCursor"]
    return total_count, add_sum, del_sum


def fetch_github_stats():
    if DRY_RUN:
        return {
            "repos": 12, "stars": 3, "followers": 5,
            "commits": 641, "loc_total": 84213,
            "loc_add": 91820, "loc_del": 7607,
        }

    viewer_q = """
    query($login:String!) {
      user(login:$login) {
        id createdAt followers { totalCount }
        repositories(first:100, ownerAffiliations:OWNER, isFork:false) {
          totalCount
          nodes { name stargazerCount }
        }
      }
    }"""
    data = gh_graphql(viewer_q, {"login": GITHUB_USERNAME})["user"]
    user_id = data["id"]
    repos = data["repositories"]["nodes"]
    stars = sum(r["stargazerCount"] for r in repos)

    # all-time commits: contributionsCollection is per-year only, so sum
    # across every year since account creation
    created_year = int(data["createdAt"][:4])
    this_year = dt.date.today().year
    commits = 0
    cc_q = """
    query($login:String!, $from:DateTime!, $to:DateTime!) {
      user(login:$login) {
        contributionsCollection(from:$from, to:$to) {
          totalCommitContributions
        }
      }
    }"""
    for year in range(created_year, this_year + 1):
        var = {"login": GITHUB_USERNAME,
               "from": f"{year}-01-01T00:00:00Z",
               "to": f"{year}-12-31T23:59:59Z"}
        cc = gh_graphql(cc_q, var)["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"]

    # lines of code, with caching so unchanged repos are skipped
    cache = load_cache(CACHE_FILE)
    archive = load_cache(ARCHIVE_FILE)
    add_total, del_total = 0, 0
    seen_names = set()
    for r in repos:
        name = r["name"]
        seen_names.add(name)
        kc, ka, kd = cache.get(name, (-1, 0, 0))
        count, add, dele = fetch_repo_loc(GITHUB_USERNAME, name, user_id, kc, ka, kd)
        cache[name] = (count, add, dele)
        add_total += add
        del_total += dele

    # repos that vanished (renamed/deleted/private) keep contributing via
    # the archive so totals don't silently drop
    for name, (c, a, d) in cache.items():
        if name not in seen_names:
            archive[name] = (c, a, d)
    for name in list(cache.keys()):
        if name not in seen_names:
            del cache[name]
    for name, (c, a, d) in archive.items():
        if name not in seen_names:
            add_total += a
            del_total += d

    save_cache(CACHE_FILE, cache)
    save_cache(ARCHIVE_FILE, archive)

    return {
        "repos": data["repositories"]["totalCount"],
        "stars": stars,
        "followers": data["followers"]["totalCount"],
        "commits": commits,
        "loc_total": add_total - del_total,
        "loc_add": add_total,
        "loc_del": del_total,
    }


STAT_FIELD_MAP = {
    "Repos": lambda s: f"{s['repos']:,}",
    "Stars": lambda s: f"{s['stars']:,}",
    "Followers": lambda s: f"{s['followers']:,}",
    "Commits": lambda s: f"{s['commits']:,}",
}


def resolve_value(label, value, stats):
    if value is not None:
        return value
    if label == "Uptime":
        return compute_uptime(BIRTHDATE)
    if label == "Lines of Code":
        return {
            "main": f"{stats['loc_total']:,}",
            "extra": [(f"{stats['loc_add']:,}++", "add"),
                      (f"{stats['loc_del']:,}--", "del")],
        }
    if label in STAT_FIELD_MAP:
        return STAT_FIELD_MAP[label](stats)
    return ""


STATS_PAIRS = [("Repos", "Stars"), ("Commits", "Followers")]

def build_lines(stats):
    """Returns an ordered list of line dicts, already filtered/wrapped/
    spaced -- ready to hand straight to the SVG renderer with sequential
    y positions."""
    lines = []
    first_section = True
    for section in SECTIONS:
        visible = [(label, resolve_value(label, value, stats))
                   for (label, value, show) in section["fields"] if show]
        visible = [(l, v) for (l, v) in visible
                   if not (isinstance(v, str) and v.strip() == "")]
        if not visible:
            continue
        if not first_section:
            lines.append({"type": "blank"})
        first_section = False
        if section["header"]:
            lines.append({"type": "header", "text": section["header"]})
        if section["header"] == "GitHub Stats":
            vmap = dict(visible)
            used = set()
            for left, right in STATS_PAIRS:
                lv, rv = vmap.get(left), vmap.get(right)
                if lv is not None and rv is not None:
                    lines.append({"type": "pair", "left": (left, lv),
                                  "right": (right, rv)})
                    used.update((left, right))
                elif lv is not None:
                    lines.append({"type": "field", "label": left, "value": lv})
                    used.add(left)
                elif rv is not None:
                    lines.append({"type": "field", "label": right, "value": rv})
                    used.add(right)
            for label, value in visible:
                if label not in used:
                    lines.append({"type": "field", "label": label, "value": value})
            continue

        for label, value in visible:
            if isinstance(value, dict):
                lines.append({"type": "field", "label": label, "value": value})
                continue
            wrapped = textwrap.wrap(str(value), VALUE_WRAP_WIDTH) or [""]
            lines.append({"type": "field", "label": label, "value": wrapped[0]})
            for cont in wrapped[1:]:
                lines.append({"type": "continuation", "value": cont})
    return lines


ROW_WIDTH = 80        # target width (chars) that values right-align to
PAIR_HALF_WIDTH = 40  # each half of a GitHub-Stats partitioned row

LABEL_COL = 30       # column where values start, for normal fields
HEADER_WIDTH = 62     # just controls how long the '- username ----' line is

def dots_for(label, col_width=LABEL_COL):
    n = max(3, col_width - len(label) - 5)
    return "." * n

def field_row_tspans(label, value, width, x=None, y=None):
    n = max(3, width - len(label) - len(str(value)) - 5)
    dots = "." * n

    first = f' x="{x}" y="{y}"' if x is not None else ""
    return (f'<tspan{first} class="cc">. </tspan>'

            f'<tspan class="key">{esc(label)}</tspan>:'

            f'<tspan class="cc"> {dots} </tspan>'

            f'<tspan class="value">{esc(value)}</tspan>')

def esc(s):

    return (str(s).replace("&", "&amp;").replace("<", "&lt;")

            .replace(">", "&gt;"))

def render_field_tspans(x, y, line):

    if line["type"] == "blank":

        return ""

    if line["type"] == "header":

        dashes = max(3, ROW_WIDTH - len(line["text"]) - 2)

        return (f'<tspan x="{x}" y="{y}" class="section">- {esc(line["text"])} '

                 f'{"-" * dashes}</tspan>')

    if line["type"] == "continuation":

        pad = max(0, ROW_WIDTH - len(line["value"]))

        return (f'<tspan x="{x}" y="{y}" class="value">'

                f'{"&#160;" * pad}{esc(line["value"])}</tspan>')

    if line["type"] == "pair":

        (llabel, lval), (rlabel, rval) = line["left"], line["right"]

        left = field_row_tspans(llabel, lval, PAIR_HALF_WIDTH, x, y)

        right = field_row_tspans(rlabel, rval, PAIR_HALF_WIDTH)

        return left + '<tspan class="cc">  |  </tspan>' + right

    label, value = line["label"], line["value"]

    if isinstance(value, dict):

        main = value["main"]

        head = field_row_tspans(label, main, ROW_WIDTH, x, y)

        extra = " ( " + ", ".join(

            f'<tspan class="{cls}">{esc(v)}</tspan>' for v, cls in value["extra"]

        ) + " )"

        return head + extra

    return field_row_tspans(label, value, ROW_WIDTH, x, y)


def build_info_svg_block(x, start_y, line_height, lines):
    out = []
    y = start_y
    for line in lines:
        if line["type"] != "blank":
            out.append(render_field_tspans(x, y, line))
        y += line_height
    return "\n    ".join(out), y


ASCII_ART = (ROOT / "ascii_art.txt").read_text().splitlines()


def build_art_svg_block(x, start_y, line_height):
    out = []
    y = start_y
    for row in ASCII_ART:
        out.append(f'<tspan x="{x}" y="{y}" xml:space="preserve">{esc(row)}</tspan>')
        y += line_height
    return "\n    ".join(out), y


PALETTES = {
    "dark": dict(bg="#0d1117", border="#30363d", header="#f8f8f2",
                 key="#e5c07b", value="#61afef", dots="#5c6370",
                 section="#e5c07b", add="#98c379", delc="#e06c75",
                 art="#abb2bf"),
    #"light": dict(bg="#ffffff", border="#d0d7de", header="#1f2328",
    #              key="#986801", value="#0969da", dots="#8c959f",
    #              section="#986801", add="#1a7f37", delc="#cf222e",
    #              art="#24292f"),
    "light": dict(bg="#0d1117", border="#30363d", header="#f8f8f8",
              key="#e5c07b", value="#61afef", dots="#5c6370",
              section="#e5c07b", add="#98c379", delc="#e06c75",
              art="#abb2bf"),
}

ART_X, ART_START_Y, ART_LINE_H = 22, 34, 15
INFO_X, INFO_START_Y, INFO_LINE_H = 470, 60, 20


def render_svg(theme):
    stats = fetch_github_stats()
    lines = build_lines(stats)
    p = PALETTES[theme]

    art_tspans, art_bottom = build_art_svg_block(ART_X, ART_START_Y, ART_LINE_H)
    info_tspans, info_bottom = build_info_svg_block(
        INFO_X, INFO_START_Y, INFO_LINE_H, lines)

    width = 1120
    height = max(art_bottom, info_bottom) + 24
    header_dashes = max(3, HEADER_WIDTH - len(DISPLAY_NAME) - 1)

    svg = f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}"
     xmlns="http://www.w3.org/2000/svg" font-family="'Cascadia Code','Fira Code',Consolas,monospace">
  <style>
    .header {{ fill: {p['header']}; font-weight: bold; font-size: 15px; }}
    .section {{ fill: {p['section']}; font-weight: bold; font-size: 13px; }}
    .key {{ fill: {p['key']}; font-size: 13px; }}
    .value {{ fill: {p['value']}; font-size: 13px; }}
    .cc {{ fill: {p['dots']}; font-size: 13px; }}
    .add {{ fill: {p['add']}; font-size: 13px; }}
    .del {{ fill: {p['delc']}; font-size: 13px; }}
    .art {{ fill: {p['art']}; font-size: 12px; }}
  </style>
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="10"
        fill="{p['bg']}" stroke="{p['border']}"/>
  <text class="header" x="{INFO_X}" y="34">{esc(DISPLAY_NAME)} {"-" * header_dashes}</text>
  <text class="art">
    {art_tspans}
  </text>
  <text>
    {info_tspans}
  </text>
</svg>
"""
    return svg


def main():
    for theme, filename in (("dark", "dark_mode.svg"), ("light", "light_mode.svg")):
        svg = render_svg(theme)
        (ROOT / filename).write_text(svg)
        print(f"wrote {filename}")


if __name__ == "__main__":
    main()
