# CI drift gating

`agentsync verify` exits **1** on drift and `--json` makes the result machine-readable,
so a PR can go red the moment someone hand-edits a rendered harness file — or changes
`config/` without re-rendering.

The pattern: the repo carries its own `.agentsync/` config (project scope) and the
rendered, committed harness files (`CLAUDE.md`, `.mcp.json`, `AGENTS.md`, …). CI re-runs
the drift check on every PR; if config and rendered files disagree, the check fails and
the JSON tells you exactly which harness and which file.

```yaml
name: agentsync drift

on: pull_request

permissions:
  contents: read

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/checkout@v4
        with:
          repository: RachidChabane/agentsync
          path: agentsync-engine
      - name: Fail on drift
        shell: bash  # explicit bash = pipefail, so tee can't swallow verify's exit 1
        run: |
          python3 -m core.agentsync verify --json \
            --project "$GITHUB_WORKSPACE" | tee drift.json
        working-directory: agentsync-engine
      - name: Summarize drift on failure
        if: failure()
        run: |
          jq -r '.harnesses[] | select(.drift) | "### \(.name)\n" +
                 ([.lines[] | select(.status=="drift") | "- \(.message)"] | join("\n"))' \
            agentsync-engine/drift.json >> "$GITHUB_STEP_SUMMARY"
```

Notes:

- To converge instead of just failing, run `agentsync apply --project .` locally and
  commit the result.
- The JSON shape: `{command, config, root, drift, docs_drift, harnesses: [{name, drift,
  lines: [{status, message}], diffs}]}`. `diffs` carries unified-diff blocks when the
  command is `diff --json`.
- Pin the engine checkout to a tag (`ref:` on the second checkout) once you depend on
  this in CI.
