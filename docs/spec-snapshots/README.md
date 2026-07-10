# Machine-managed — don't hand-edit

Normalized snapshots of the upstream doc pages listed in `../spec-sources.json`.
`python3 -m core.spec_watch` diffs the live pages against these weekly (CI cron) and
opens an issue on drift; `--update` regenerates them after an adapter is fixed.
