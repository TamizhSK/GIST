# Real-workflow corpus

The "% of real-world syntax supported" metric in the demo. Each file is a
**vendored, byte-exact** GitHub Actions workflow from a real OSS repository —
not a fixture we wrote. The parametrized test in `tests/unit/test_corpus.py`
asserts each one parses without `E1xx`/`E2xx` and builds IR.

Rules for this directory:

- **Real only.** Copy the file verbatim from its upstream repo. Do not edit it
  to make it pass — if it fails, that is a hole in yeet, and the fix belongs in
  the schema or builder, not in the file.
- **Record provenance.** Every file's row below must say which repo, branch,
  path and commit SHA it was vendored from, so a regression can be pinned to a
  specific upstream revision.
- **LF only.** `.gitattributes` enforces `eol=lf` here (see the `W006` gate).

Provenance (vendored 2026-08-12):

| File | Upstream | Branch | Path | Commit SHA |
|---|---|---|---|---|
| `checkout.yml` | actions/checkout | main | `.github/workflows/check-dist.yml` | `4f1f4aec02e41874fa0262ea8ff5172d7978ad1e` |
| `numpy.yml` | numpy/numpy | main | `.github/workflows/linux.yml` | `702a2599f247b8dc07180ec1fc449bf49be77ed0` |
| `curl.yml` | curl/curl | master | `.github/workflows/linux.yml` | `8a8ff47b63aff1d72c1796dbdb4955f243beac23` |
| `pandas-unit-tests.yml` | pandas-dev/pandas | main | `.github/workflows/unit-tests.yml` | `7bb284ac438d2b981a7f42e3bdd0fe5ee26aada0` |
| `sklearn-unit-tests.yml` | scikit-learn/scikit-learn | main | `.github/workflows/unit-tests.yml` | `7c42ab63c7fb4bcc5ad36372a8f829fffb3d487e` |
| `black-test.yml` | psf/black | main | `.github/workflows/test.yml` | `fa72105efac5c15c3a3c83c21ec6e6097c525325` |
| `flask-tests.yaml` | pallets/flask | main | `.github/workflows/tests.yaml` | `6a2f545bfd8ed31e19066a299296917e034aca58` |
| `pytest-test.yml` | pytest-dev/pytest | main | `.github/workflows/test.yml` | `ecade5a6c120732f94126c806c40bee12c98398a` |
| `jinja-tests.yaml` | pallets/jinja | main | `.github/workflows/tests.yaml` | `0cc6ff9051d6fe527e0d386c775f032ed51032c0` |

What the corpus buys us that the golden fixtures can't:

- **Schema holes.** Real workflows use `permissions`, `concurrency`, `services`,
  job-level `continue-on-error`, numeric `env` values and expression-valued
  `timeout-minutes` — every one of those was a `E201`/`E203` regression the
  hand-written fixtures never exercised. The corpus is what found them.
- **A tripwire for the dialect claim.** "A superset, not a replacement" is only
  true if a file we didn't write still validates; the golden fixtures are all
  ours and can't test that.

Known non-parse findings the corpus surfaces (deliberately NOT asserted here —
they are layer-3/layer-4 concerns owned elsewhere):

- `flask-tests.yaml`, `jinja-tests.yaml`, `sklearn-unit-tests.yml` fire a
  spurious `E303` ("empty matrix") because they define their matrix entirely
  through `include:` — legal GitHub that `layer3_semantic.py` doesn't allow.
- `checkout.yml`/`curl.yml`/`numpy.yml`/`pandas-unit-tests.yml` trip W402/W403/
  W404/W405/W409 lints (moving refs, `:latest`, a planted-looking token, shell
  without `set -euo pipefail`, absolute paths). Those are lint findings, not
  parse failures, and exactly what `yeet check` is for.
