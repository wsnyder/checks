"""Tiny GitHub REST helper + /check command parsing. Stdlib only."""
import json
import os
import re
import urllib.request
import urllib.error

API = os.environ.get("GITHUB_API_URL", "https://api.github.com")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
PREFIX = "check/"
DEFAULT_ID = "default"
HELP_MARKER = "<!-- check-help -->"

# command word -> conclusion
CONCLUSIONS = {
    "success": "success", "pass": "success",
    "failure": "failure", "fail": "failure",
    "neutral": "neutral",
    "cancelled": "cancelled",
    "skipped": "skipped",
    "timed_out": "timed_out", "timeout": "timed_out",
    "action_required": "action_required",
}
OTHER = {"start", "status", "title", "note", "list"}
COMMANDS = set(CONCLUSIONS) | OTHER
LEVELS = ("notice", "warning", "failure")

HELP = """## `/check` commands

Comment on this PR to update its checks. Syntax: `/check [<id>] <command> [text]`

- `<id>` (`[A-Za-z0-9_.-]`, max 40 chars) selects the check run `check/<id>`; default is `default`.
  Different ids are independent checks. Unknown ids are created on first use.
- Conclusions (mark the check completed): `success` (`pass`), `failure` (`fail`), `neutral`,
  `cancelled`, `skipped`, `timed_out` (`timeout`), `action_required`. Optional text becomes the summary.
- `start [title]` - create the check / set it in progress
- `status queued|in_progress` - change status
- `title <text>` - set the output title
- `note [notice|warning|failure] <text>` - append to the summary and annotate the first changed file
- `list` - post a table of this PR's checks

Examples:
```
/check build start Compiling
/check lint failure 3 errors
/check build success
/check perf note warning 5% slower than baseline
/check list
```
Put several commands in one comment, one per line; other lines are ignored.
Only owners, members and collaborators can use these. `/checks` is accepted as an alias.
"""


def api(method, path, body=None):
    url = path if path.startswith("http") else f"{API}/repos/{REPO}{path}"
    if os.environ.get("CHECKS_DRY_RUN"):
        print(method, url, json.dumps(body))
        return {"check_runs": []} if method == "GET" else {}
    req = urllib.request.Request(
        url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
    try:
        with urllib.request.urlopen(req) as r:
            data = r.read()
            return json.loads(data) if data else {}
    except urllib.error.HTTPError as e:
        raise SystemExit(f"{method} {url} -> {e.code}: {e.read().decode()}")


def list_checks(sha):
    runs = api("GET", f"/commits/{sha}/check-runs?per_page=100")
    return [r for r in runs["check_runs"] if r["name"].startswith(PREFIX)]


def find_check(sha, cid):
    for r in list_checks(sha):
        if r["name"] == PREFIX + cid:
            return r
    return None


def create_check(sha, cid, status="in_progress", title=None, summary=""):
    return api("POST", "/check-runs", {
        "name": PREFIX + cid, "head_sha": sha, "status": status,
        "output": {"title": title or cid, "summary": summary or "(no summary)"},
    })


def update_check(run, **fields):
    return api("PATCH", f"/check-runs/{run['id']}", fields)


def post_comment(number, text):
    return api("POST", f"/issues/{number}/comments", {"body": text})


class NotACommand(Exception):
    """Comment merely starts with /check (e.g. `/checkout`); ignore it silently."""


def parse(line):
    """Parse one line into (id, cmd, args). Raises ValueError with a user-facing
    message, or NotACommand if the line isn't a /check command at all."""
    m = re.match(r"^/checks?(?:\s+(.*))?$", line.strip())
    if not m:
        raise NotACommand()
    toks = (m.group(1) or "").split()
    if not toks:
        raise ValueError("")  # empty message -> caller shows help
    if toks[0].lower() in COMMANDS:
        cid, cmd, args = DEFAULT_ID, toks[0].lower(), toks[1:]
    else:
        cid = toks[0]
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,40}", cid):
            raise ValueError(f"invalid id `{cid}`")
        if len(toks) < 2 or toks[1].lower() not in COMMANDS:
            raise ValueError(f"unknown or missing command after id `{cid}`")
        cmd, args = toks[1].lower(), toks[2:]
    return cid, cmd, " ".join(args)
