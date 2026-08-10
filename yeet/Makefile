# Run `make check` before every push. It is the same set CI runs, so a green
# local run means a green PR — that is the whole point of it being ten lines.
.PHONY: check lint fmt imports types test docker rules all

check: lint imports types test

lint:
	ruff check src tests

fmt:
	ruff check src tests --fix
	ruff format src tests

imports:            ## the tier rule from docs/architecture.md — run before every push
	lint-imports

types:
	mypy src

test:               ## fast loop — run this constantly
	pytest -m "not docker" -q

docker:             ## needs the daemon
	pytest -m docker -q

rules:              ## regenerate docs/rules.md from core/codes.py — never hand-edit it
	@test -f tools/gen_rules_doc.py || { \
	  echo "tools/gen_rules_doc.py does not exist yet — that script is Dev D / task D18."; \
	  echo "It generates docs/rules.md from core/codes.py so the two cannot drift."; \
	  exit 1; }
	python tools/gen_rules_doc.py

all: fmt check
