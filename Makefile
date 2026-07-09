# Deterministic front door for agentsync itself (it dogfoods its own protocol).
.PHONY: help init apply verify test

help:  ## list verbs
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-8s %s\n",$$1,$$2}'

init:  ## detect harnesses, create config/, apply, install scaffolder
	@./init.sh

apply:  ## render config into every enabled harness
	@python3 -m core.agentsync apply

# 'verify' = fast, read-only, commit-safe. The commit gate runs this.
verify:  ## syntax-check all sources + run the test suite (no writes to $HOME)
	@python3 -m py_compile core/*.py core/adapters/*.py skills/*/*.py && echo "· python ok"
	@for f in core/enforcement/*.sh init.sh install.sh skills/*/*.sh tests/*.sh; do bash -n "$$f" || exit 1; done && echo "· bash ok"
	@node --check core/enforcement/opencode-plugin.js && echo "· node ok"
	@for f in config.example/*.json; do python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$$f" || exit 1; done && echo "· json ok"
	@python3 -c "import tomllib;tomllib.load(open('pyproject.toml','rb'))" && echo "· toml ok"
	@bash tests/test_runner.sh
	@bash tests/test_scaffold.sh
	@python3 tests/test_apply.py
	@python3 tests/test_project.py
	@python3 tests/test_lifecycle.py
	@python3 tests/test_skills.py
	@python3 tests/test_docs.py

test: verify  ## alias for verify (suite is fast)
