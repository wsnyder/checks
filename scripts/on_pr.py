"""pull_request handler: ensure check/default exists; post the help comment once."""
import json
import os

import checks_api as c

ev = json.load(open(os.environ["GITHUB_EVENT_PATH"]))
pr = ev["pull_request"]
sha, num = pr["head"]["sha"], pr["number"]

if not c.find_check(sha, c.DEFAULT_ID):
    c.create_check(sha, c.DEFAULT_ID, title="Experiment check",
                   summary="Created on PR event. Comment `/check` for help.")

if ev["action"] == "opened":
    comments = c.api("GET", f"/issues/{num}/comments?per_page=100")
    if not any(c.HELP_MARKER in x.get("body", "") for x in comments):
        c.post_comment(num, c.HELP_MARKER + "\n" + c.HELP)
