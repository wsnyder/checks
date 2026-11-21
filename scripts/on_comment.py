"""issue_comment handler: parse a /check command and update the Checks API.

Local parse test:  python3 scripts/on_comment.py --dry-run "/check build fail 3 errors"
"""
import datetime
import json
import os
import sys

import checks_api as c


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_command(num, sha, cid, cmd, text):
    run = c.find_check(sha, cid)
    out = (run or {}).get("output") or {}

    if cmd == "list":
        rows = ["| id | status | conclusion | title |", "|---|---|---|---|"]
        for r in c.list_checks(sha):
            rows.append(f"| {r['name'][len(c.PREFIX):]} | {r['status']} | "
                        f"{r['conclusion'] or ''} | {(r['output'] or {}).get('title') or ''} |")
        c.post_comment(num, "\n".join(rows))
        return

    if cmd == "start":
        if run:
            c.update_check(run, status="in_progress",
                           output={"title": text or out.get("title") or cid,
                                   "summary": out.get("summary") or "(no summary)"})
        else:
            c.create_check(sha, cid, title=text)
        return

    if not run:
        run = c.create_check(sha, cid)
        out = run.get("output") or {}

    if cmd in c.CONCLUSIONS:
        concl = c.CONCLUSIONS[cmd]
        c.update_check(run, status="completed", conclusion=concl, completed_at=now(),
                       output={"title": text or concl, "summary": text or concl})
    elif cmd == "status":
        if text not in ("queued", "in_progress"):
            raise ValueError("status must be `queued` or `in_progress`")
        c.update_check(run, status=text)
    elif cmd == "title":
        if not text:
            raise ValueError("title needs text")
        c.update_check(run, output={"title": text,
                                    "summary": out.get("summary") or "(no summary)"})
    elif cmd == "note":
        level, _, rest = text.partition(" ")
        if level.lower() in c.LEVELS:
            level, text = level.lower(), rest.strip()
        else:
            level = "notice"
        if not text:
            raise ValueError("note needs text")
        output = {"title": out.get("title") or cid,
                  "summary": ((out.get("summary") or "") + f"\n- **{level}**: {text}").strip()}
        files = c.api("GET", f"/pulls/{num}/files?per_page=1")
        if files:
            output["annotations"] = [{"path": files[0]["filename"], "start_line": 1,
                                      "end_line": 1, "annotation_level": level,
                                      "message": text}]
        c.update_check(run, output=output)


def main():
    if sys.argv[1:2] == ["--dry-run"]:
        os.environ["CHECKS_DRY_RUN"] = "1"
        try:
            print(c.parse(sys.argv[2]))
        except ValueError as e:
            print("error:", e or "(help)")
        except c.NotACommand:
            print("ignored")
        return

    ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
    num, comment = ev["issue"]["number"], ev["comment"]
    if "pull_request" not in ev["issue"]:
        return
    if comment["author_association"] not in ("OWNER", "MEMBER", "COLLABORATOR"):
        return
    try:
        cid, cmd, text = c.parse(comment["body"])
    except c.NotACommand:
        return
    except ValueError as e:
        c.post_comment(num, (f"Error: {e}\n\n" if str(e) else "") + c.HELP)
        return
    sha = c.api("GET", f"/pulls/{num}")["head"]["sha"]
    try:
        run_command(num, sha, cid, cmd, text)
    except ValueError as e:
        c.post_comment(num, f"Error: {e}")
        return
    c.api("POST", f"/issues/comments/{comment['id']}/reactions", {"content": "+1"})


main()
