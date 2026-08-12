# Run `make check` before every push. It is the same set CI runs, so a green
# local run means a green PR — that is the whole point of it being short.
#
# `format` and `noprint` are in `check` deliberately. CI ran `ruff format
# --check` while `make check` did not, so a tree could be locally green and
# fail on the first push — which is exactly what happened, twice.
.PHONY: check lint format imports types test noprint rules-check docker image rules fmt fix all

check: lint format imports types noprint test

lint:
	ruff check src tests

format:             ## the gate CI runs; `make fix` is what repairs it
	ruff format --check src tests

imports:            ## the tier rule from docs/architecture.md — run before every push
	lint-imports

types:
	mypy src

noprint:            ## risk register #2 — user-facing output is a Diagnostic or typer.echo
	python tools/check_no_print.py src

test:               ## fast loop — run this constantly
	pytest -m "not docker" -q

rules-check:        ## docs/rules.md must match core/codes.py
	@python tools/gen_rules_doc.py >/dev/null
	@git diff --quiet -- docs/rules.md \
	  || { echo "docs/rules.md is stale — run 'make rules' and commit it."; exit 1; }

docker:             ## needs the daemon
	pytest -m docker -q

image:              ## build the base image every `cooked_on: ubuntu-latest` job runs in
	docker build -f Dockerfile.base -t yeet/ubuntu:22.04 .

rules:              ## regenerate docs/rules.md from core/codes.py — never hand-edit it
	python tools/gen_rules_doc.py

fix:                ## repair what `make check` complains about
	ruff check src tests --fix
	ruff format src tests

fmt: fix            ## alias, muscle memory

all: fix check
