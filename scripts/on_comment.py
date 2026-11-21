"""issue_comment handler: parse /check commands (one per line) and update the Checks API.

Local parse test:  python3 scripts/on_comment.py --dry-run "/check build fail 3 errors"
"""
import datetime
import json
import os
import sys

import checks_api as c


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_command(num, sha, runs, cid, cmd, text):
    """`runs` caches this PR head's checks by id for the whole comment.
    Returns a one-line description of what was done (None for `list`)."""
    def save(r):
        if r.get("id"):
            runs[cid] = r
        return r

    run = runs.get(cid)
    out = (run or {}).get("output") or {}

    if cmd == "list":
        rows = ["| id | status | conclusion | title |", "|---|---|---|---|"]
        for i, r in sorted(runs.items()):
            rows.append(f"| {i} | {r['status']} | "
                        f"{r.get('conclusion') or ''} | {(r['output'] or {}).get('title') or ''} |")
        c.post_comment(num, "\n".join(rows))
        return None

    if cmd == "start":
        if run:
            save(c.update_check(run, status="in_progress",
                                output={"title": text or out.get("title") or cid,
                                        "summary": out.get("summary") or "(no summary)"}))
            return f"`{cid}`: set to in_progress" + (f", title \"{text}\"" if text else "")
        save(c.create_check(sha, cid, title=text))
        return f"`{cid}`: created, in_progress" + (f", title \"{text}\"" if text else "")

    # Validate before auto-creating, so a bad command leaves no stray check.
    if cmd == "status" and text not in ("queued", "in_progress"):
        raise ValueError("status must be `queued` or `in_progress`")
    if cmd == "title" and not text:
        raise ValueError("title needs text")
    level = "notice"
    if cmd == "note":
        first, _, rest = text.partition(" ")
        if first.lower() in c.LEVELS:
            level, text = first.lower(), rest.strip()
        if not text:
            raise ValueError("note needs text")

    created = not run
    if created:
        run = save(c.create_check(sha, cid))
        out = run.get("output") or {}

    if cmd in c.CONCLUSIONS:
        concl = c.CONCLUSIONS[cmd]
        save(c.update_check(run, status="completed", conclusion=concl, completed_at=now(),
                            output={"title": text or concl, "summary": text or concl}))
        done = f"completed with conclusion `{concl}`" + (f": {text}" if text else "")
    elif cmd == "status":
        save(c.update_check(run, status=text))
        done = f"status set to {text}"
    elif cmd == "title":
        save(c.update_check(run, output={"title": text,
                                         "summary": out.get("summary") or "(no summary)"}))
        done = f"title set to \"{text}\""
    elif cmd == "note":
        output = {"title": out.get("title") or cid,
                  "summary": ((out.get("summary") or "") + f"\n- **{level}**: {text}").strip()}
        files = c.api("GET", f"/pulls/{num}/files?per_page=1")
        if files:
            output["annotations"] = [{"path": files[0]["filename"], "start_line": 1,
                                      "end_line": 1, "annotation_level": level,
                                      "message": text}]
        save(c.update_check(run, output=output))
        done = f"added {level} note" + (" with annotation" if files else "") + f": {text}"
    return f"`{cid}`: " + ("created; " if created else "") + done


def main():
    if sys.argv[1:2] == ["--dry-run"]:
        os.environ["CHECKS_DRY_RUN"] = "1"
        for line in sys.argv[2].splitlines():
            try:
                print(c.parse(line))
            except ValueError as e:
                print("error:", e or "(help)")
            except c.NotACommand:
                pass
        return

    ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
    num, comment = ev["issue"]["number"], ev["comment"]
    if "pull_request" not in ev["issue"]:
        return
    if comment["author_association"] not in ("OWNER", "MEMBER", "COLLABORATOR"):
        return

    # Parse every line first so we only touch the API if something is a command.
    cmds, errors, show_help = [], [], False
    for line in comment["body"].splitlines():
        try:
            cmds.append(c.parse(line))
        except c.NotACommand:
            continue
        except ValueError as e:
            if str(e):
                errors.append(f"`{line.strip()}`: {e}")
            else:
                show_help = True
    if not cmds and not errors and not show_help:
        return

    done = []
    if cmds:
        sha = c.api("GET", f"/pulls/{num}")["head"]["sha"]
        runs = {r["name"][len(c.PREFIX):]: r for r in c.list_checks(sha)}
        for cid, cmd, text in cmds:
            try:
                line = run_command(num, sha, runs, cid, cmd, text)
                if line:
                    done.append(line)
            except ValueError as e:
                errors.append(f"`/check {cid} {cmd} {text}`: {e}")

    parts = []
    if done:
        parts.append(f"Updated checks on `{sha[:7]}`:\n" + "\n".join(f"- {d}" for d in done))
    if errors:
        parts.append("Errors:\n" + "\n".join(f"- {e}" for e in errors))
    if errors or show_help:
        parts.append(c.HELP)
    if parts:
        c.post_comment(num, "\n\n".join(parts))


main()
