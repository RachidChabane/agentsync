# CI drift gating

`agentsync verify` exits **1** on drift and `--json` makes the result machine-readable,
so a PR can go red the moment someone hand-edits a rendered harness file — or changes
`config/` without re-rendering.

The pattern: keep your `config/` and the rendered harness files (`rendered/`, played by
`--root`) in the same repo. CI re-runs the drift check on every PR; if the two disagree,
the check fails and the JSON tells you exactly which harness and which file.

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
          path: .agentsync
      - name: Fail on drift
        run: |
          python3 -m core.agentsync verify --json \
            --config "$GITHUB_WORKSPACE/config" \
            --root "$GITHUB_WORKSPACE/rendered" \
            --no-mcp-import | tee drift.json
        working-directory: .agentsync
      - name: Summarize drift on failure
        if: failure()
        run: |
          jq -r '.harnesses[] | select(.drift) | "### \(.name)\n" +
                 ([.lines[] | select(.status=="drift") | "- \(.message)"] | join("\n"))' \
            .agentsync/drift.json >> "$GITHUB_STEP_SUMMARY"
```

Notes:

- `--no-mcp-import` skips the Claude-CLI import step, which only makes sense on a real
  workstation (`$HOME` + the `claude` CLI).
- To converge instead of just failing, run `apply` with the same flags locally and commit
  the result.
- The JSON shape: `{command, config, root, drift, docs_drift, harnesses: [{name, drift,
  lines: [{status, message}], diffs}]}`. `diffs` carries unified-diff blocks when the
  command is `diff --json`.
- Pin `.agentsync` to a tag (`ref:` on the second checkout) once you depend on this in CI.
