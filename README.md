# checks

Rough experiment: drive the GitHub Checks API from PR comments, using only GitHub Actions.

- Opening a PR creates check run `check/default` and posts a help comment.
- Comments like `/check build fail 3 errors` create/update check run `check/<id>`.

## Try it
1. Push this repo to GitHub and merge the workflows to the default branch
   (`issue_comment` workflows always run from the default branch).
2. Open a PR from a branch in the same repo (fork PRs get a read-only token).
3. Comment `/check` for help, `/check build start`, `/check build success`, `/check list`.

## Commands
`/check [<id>] <command> [text]` (also `/checks`). Default id is `default`.

- Conclusions: `success`(`pass`) `failure`(`fail`) `neutral` `cancelled` `skipped` `timed_out`(`timeout`) `action_required`
- `start [title]`, `status queued|in_progress`, `title <text>`, `note [notice|warning|failure] <text>`, `list`

Only OWNER/MEMBER/COLLABORATOR comments are honored. Checks appear under the "github-actions" app.

## Local parse test
    python3 scripts/on_comment.py --dry-run "/check build fail 3 errors"
