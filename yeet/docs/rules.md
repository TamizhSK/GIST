# yeet Diagnostic Rules Reference

*Auto-generated from `src/yeet/core/codes.py` by `tools/gen_rules_doc.py` —
do not hand-edit. Run `make rules` after adding a code.*

Every diagnostic yeet can emit. `yeet explain YEET-E301` prints one section.

- **E**rrors block: `yeet check` exits 2 and `yeet run` refuses to start.
- **W**arnings print and do not block, unless `--strict` or a `.yeet/lint.yml`
  override promotes them.
- **I**nfo is advisory only.

Layer 4 codes can be reconfigured per project in `.yeet/lint.yml`:

```yaml
YEET-W403: error    # promote — now blocks
YEET-W407: off      # silence entirely
```


## Layer 0 — File & Encoding

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-E001`](#yeet-e001) | `error` | file unreadable or missing |
| [`YEET-E002`](#yeet-e002) | `error` | file is empty |
| [`YEET-E003`](#yeet-e003) | `error` | non-UTF-8 character encoding |
| [`YEET-E005`](#yeet-e005) | `error` | tabs used for indentation |
| [`YEET-W004`](#yeet-w004) | `warning` | UTF-8 BOM present |
| [`YEET-W006`](#yeet-w006) | `warning` | CRLF line endings |
| [`YEET-W007`](#yeet-w007) | `warning` | file size exceeds 1 MB |

---

### `YEET-E001` — file unreadable or missing

- **Layer:** 0 (Layer 0 — File & Encoding)
- **Default severity:** `error`
- **Meaning:** file unreadable or missing.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E002` — file is empty

- **Layer:** 0 (Layer 0 — File & Encoding)
- **Default severity:** `error`
- **Meaning:** file is empty.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E003` — non-UTF-8 character encoding

- **Layer:** 0 (Layer 0 — File & Encoding)
- **Default severity:** `error`
- **Meaning:** non-UTF-8 character encoding.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E005` — tabs used for indentation

- **Layer:** 0 (Layer 0 — File & Encoding)
- **Default severity:** `error`
- **Meaning:** tabs used for indentation.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-W004` — UTF-8 BOM present

- **Layer:** 0 (Layer 0 — File & Encoding)
- **Default severity:** `warning`
- **Meaning:** UTF-8 BOM present.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-W006` — CRLF line endings

- **Layer:** 0 (Layer 0 — File & Encoding)
- **Default severity:** `warning`
- **Meaning:** CRLF line endings.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-W007` — file size exceeds 1 MB

- **Layer:** 0 (Layer 0 — File & Encoding)
- **Default severity:** `warning`
- **Meaning:** file size exceeds 1 MB.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

## Layer 1 — YAML Syntax

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-E101`](#yeet-e101) | `error` | YAML parse failure |
| [`YEET-E102`](#yeet-e102) | `error` | duplicate key |
| [`YEET-E103`](#yeet-e103) | `error` | top-level document is not a mapping |
| [`YEET-E104`](#yeet-e104) | `error` | multi-document YAML is not allowed |
| [`YEET-W105`](#yeet-w105) | `warning` | unquoted `on` parsed as a boolean |

---

### `YEET-E101` — YAML parse failure

- **Layer:** 1 (Layer 1 — YAML Syntax)
- **Default severity:** `error`
- **Meaning:** YAML parse failure.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E101.yml`:

```yaml
on: push
jobs:
  build:
    steps:
      - run: "echo hi
```

---

### `YEET-E102` — duplicate key

- **Layer:** 1 (Layer 1 — YAML Syntax)
- **Default severity:** `error`
- **Meaning:** duplicate key.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E102.yml`:

```yaml
on: push
jobs:
  build:
    steps:
      - run: "echo hi"
        run: "echo bye"
```

---

### `YEET-E103` — top-level document is not a mapping

- **Layer:** 1 (Layer 1 — YAML Syntax)
- **Default severity:** `error`
- **Meaning:** top-level document is not a mapping.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E103.yml`:

```yaml
- on: push
- jobs: {}
```

---

### `YEET-E104` — multi-document YAML is not allowed

- **Layer:** 1 (Layer 1 — YAML Syntax)
- **Default severity:** `error`
- **Meaning:** multi-document YAML is not allowed.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E104.yml`:

```yaml
on: push
---
jobs:
  build:
    steps:
      - run: "echo hi"
```

---

### `YEET-W105` — unquoted `on` parsed as a boolean

- **Layer:** 1 (Layer 1 — YAML Syntax)
- **Default severity:** `warning`
- **Meaning:** unquoted `on` parsed as a boolean.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/W105.yml`:

```yaml
True: push
jobs:
  build:
    steps:
      - run: "echo hi"
```

---

## Layer 2 — Schema Validation

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-E201`](#yeet-e201) | `error` | unknown key |
| [`YEET-E202`](#yeet-e202) | `error` | required key missing |
| [`YEET-E203`](#yeet-e203) | `error` | invalid data type |
| [`YEET-E204`](#yeet-e204) | `error` | step has both `run` and `uses` |
| [`YEET-E205`](#yeet-e205) | `error` | step has neither `run` nor `uses` |
| [`YEET-E206`](#yeet-e206) | `error` | no jobs defined |
| [`YEET-E207`](#yeet-e207) | `error` | invalid job id |
| [`YEET-E208`](#yeet-e208) | `error` | unsupported event name |

---

### `YEET-E201` — unknown key

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** unknown key.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E201.yml`:

```yaml
on: push
jobs:
  build:
    steps:
      - run: "echo hi"
foo: bar
```

---

### `YEET-E202` — required key missing

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** required key missing.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E202.yml`:

```yaml
jobs:
  build:
    steps:
      - run: "echo hi"
```

---

### `YEET-E203` — invalid data type

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** invalid data type.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E203.yml`:

```yaml
on: 5
jobs:
  build:
    steps:
      - run: "echo hi"
```

---

### `YEET-E204` — step has both `run` and `uses`

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** step has both `run` and `uses`.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E204.yml`:

```yaml
on: push
jobs:
  build:
    steps:
      - run: "echo hi"
        uses: "./.yeet/actions/checkout"
```

---

### `YEET-E205` — step has neither `run` nor `uses`

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** step has neither `run` nor `uses`.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E205.yml`:

```yaml
on: push
jobs:
  build:
    steps:
      - name: "nothing here"
```

---

### `YEET-E206` — no jobs defined

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** no jobs defined.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E206.yml`:

```yaml
on: push
jobs: {}
```

---

### `YEET-E207` — invalid job id

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** invalid job id.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E207.yml`:

```yaml
on: push
jobs:
  "9 lives":
    steps:
      - run: "echo hi"
```

---

### `YEET-E208` — unsupported event name

- **Layer:** 2 (Layer 2 — Schema Validation)
- **Default severity:** `error`
- **Meaning:** unsupported event name.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

A workflow that triggers it — `tests/invalid/E208.yml`:

```yaml
on: [qwerty]
jobs:
  build:
    steps:
      - run: "echo hi"
```

---

## Layer 3 — Semantic Validation

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-E301`](#yeet-e301) | `error` | `needs` references an unknown job |
| [`YEET-E302`](#yeet-e302) | `error` | dependency cycle |
| [`YEET-E303`](#yeet-e303) | `error` | invalid matrix configuration |
| [`YEET-E304`](#yeet-e304) | `error` | duplicate job id |
| [`YEET-E305`](#yeet-e305) | `error` | invalid environment variable name |
| [`YEET-E306`](#yeet-e306) | `error` | invalid container image format |
| [`YEET-E307`](#yeet-e307) | `error` | missing secret reference |
| [`YEET-E308`](#yeet-e308) | `error` | invalid action reference |
| [`YEET-E309`](#yeet-e309) | `error` | expression fails to parse |
| [`YEET-E310`](#yeet-e310) | `error` | expression references unknown context |
| [`YEET-E311`](#yeet-e311) | `error` | expression references unknown function |
| [`YEET-E312`](#yeet-e312) | `error` | invalid expression position |
| [`YEET-E313`](#yeet-e313) | `error` | `uses:` could not be resolved |
| [`YEET-E314`](#yeet-e314) | `error` | missing required action input |
| [`YEET-E315`](#yeet-e315) | `error` | `cooked_on:` could not be resolved to an image |
| [`YEET-E316`](#yeet-e316) | `error` | invalid runner specification |
| [`YEET-W317`](#yeet-w317) | `warning` | deprecated workflow syntax |
| [`YEET-W318`](#yeet-w318) | `warning` | unused output variable |
| [`YEET-W319`](#yeet-w319) | `warning` | `with:` supplies an input the action does not declare |

---

### `YEET-E301` — `needs` references an unknown job

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** `needs` references an unknown job.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E302` — dependency cycle

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** dependency cycle.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E303` — invalid matrix configuration

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** invalid matrix configuration.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E304` — duplicate job id

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** duplicate job id.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E305` — invalid environment variable name

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** invalid environment variable name.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E306` — invalid container image format

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** invalid container image format.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E307` — missing secret reference

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** missing secret reference.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E308` — invalid action reference

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** invalid action reference.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E309` — expression fails to parse

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** expression fails to parse.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E310` — expression references unknown context

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** expression references unknown context.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E311` — expression references unknown function

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** expression references unknown function.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E312` — invalid expression position

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** invalid expression position.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E313` — `uses:` could not be resolved

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** `uses:` could not be resolved.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E314` — missing required action input

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** missing required action input.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E315` — `cooked_on:` could not be resolved to an image

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** `cooked_on:` could not be resolved to an image.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-E316` — invalid runner specification

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `error`
- **Meaning:** invalid runner specification.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-W317` — deprecated workflow syntax

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `warning`
- **Meaning:** deprecated workflow syntax.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-W318` — unused output variable

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `warning`
- **Meaning:** unused output variable.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

### `YEET-W319` — `with:` supplies an input the action does not declare

- **Layer:** 3 (Layer 3 — Semantic Validation)
- **Default severity:** `warning`
- **Meaning:** `with:` supplies an input the action does not declare.
- **Disabling:** Not configurable: layers 0-3 are correctness checks, and a workflow that fails one of them cannot be run faithfully.

---

## Layer 4 — Lint & Code Standards

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-I415`](#yeet-i415) | `info` | mixed dialect and canonical keys |
| [`YEET-W401`](#yeet-w401) | `warning` | missing name |
| [`YEET-W402`](#yeet-w402) | `warning` | action pinned to a moving ref |
| [`YEET-W403`](#yeet-w403) | `warning` | image pinned to :latest tag |
| [`YEET-W404`](#yeet-w404) | `warning` | possible hardcoded secret |
| [`YEET-W405`](#yeet-w405) | `warning` | multi-line run without `set -euo pipefail` |
| [`YEET-W406`](#yeet-w406) | `warning` | run step exceeds 50 lines |
| [`YEET-W407`](#yeet-w407) | `warning` | job has no timeout |
| [`YEET-W408`](#yeet-w408) | `warning` | continue-on-error on deploy job |
| [`YEET-W409`](#yeet-w409) | `warning` | absolute host path in workflow |
| [`YEET-W410`](#yeet-w410) | `warning` | path case mismatch with disk |
| [`YEET-W411`](#yeet-w411) | `warning` | deprecated command format |
| [`YEET-W412`](#yeet-w412) | `warning` | EOL action version |
| [`YEET-W413`](#yeet-w413) | `warning` | zero steps in job |
| [`YEET-W414`](#yeet-w414) | `warning` | duplicated step block across jobs |

---

### `YEET-I415` — mixed dialect and canonical keys

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `info`
- **Meaning:** mixed dialect and canonical keys.
- **Disabling:** Set `YEET-I415: off` in `.yeet/lint.yml` to silence it, or `YEET-I415: error` to make it blocking.

---

### `YEET-W401` — missing name

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** missing name.
- **Disabling:** Set `YEET-W401: off` in `.yeet/lint.yml` to silence it, or `YEET-W401: error` to make it blocking.

---

### `YEET-W402` — action pinned to a moving ref

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** action pinned to a moving ref.
- **Disabling:** Set `YEET-W402: off` in `.yeet/lint.yml` to silence it, or `YEET-W402: error` to make it blocking.

---

### `YEET-W403` — image pinned to :latest tag

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** image pinned to :latest tag.
- **Disabling:** Set `YEET-W403: off` in `.yeet/lint.yml` to silence it, or `YEET-W403: error` to make it blocking.

---

### `YEET-W404` — possible hardcoded secret

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** possible hardcoded secret.
- **Disabling:** Set `YEET-W404: off` in `.yeet/lint.yml` to silence it, or `YEET-W404: error` to make it blocking.

---

### `YEET-W405` — multi-line run without `set -euo pipefail`

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** multi-line run without `set -euo pipefail`.
- **Disabling:** Set `YEET-W405: off` in `.yeet/lint.yml` to silence it, or `YEET-W405: error` to make it blocking.

---

### `YEET-W406` — run step exceeds 50 lines

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** run step exceeds 50 lines.
- **Disabling:** Set `YEET-W406: off` in `.yeet/lint.yml` to silence it, or `YEET-W406: error` to make it blocking.

---

### `YEET-W407` — job has no timeout

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** job has no timeout.
- **Disabling:** Set `YEET-W407: off` in `.yeet/lint.yml` to silence it, or `YEET-W407: error` to make it blocking.

---

### `YEET-W408` — continue-on-error on deploy job

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** continue-on-error on deploy job.
- **Disabling:** Set `YEET-W408: off` in `.yeet/lint.yml` to silence it, or `YEET-W408: error` to make it blocking.

---

### `YEET-W409` — absolute host path in workflow

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** absolute host path in workflow.
- **Disabling:** Set `YEET-W409: off` in `.yeet/lint.yml` to silence it, or `YEET-W409: error` to make it blocking.

---

### `YEET-W410` — path case mismatch with disk

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** path case mismatch with disk.
- **Disabling:** Set `YEET-W410: off` in `.yeet/lint.yml` to silence it, or `YEET-W410: error` to make it blocking.

---

### `YEET-W411` — deprecated command format

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** deprecated command format.
- **Disabling:** Set `YEET-W411: off` in `.yeet/lint.yml` to silence it, or `YEET-W411: error` to make it blocking.

---

### `YEET-W412` — EOL action version

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** EOL action version.
- **Disabling:** Set `YEET-W412: off` in `.yeet/lint.yml` to silence it, or `YEET-W412: error` to make it blocking.

---

### `YEET-W413` — zero steps in job

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** zero steps in job.
- **Disabling:** Set `YEET-W413: off` in `.yeet/lint.yml` to silence it, or `YEET-W413: error` to make it blocking.

---

### `YEET-W414` — duplicated step block across jobs

- **Layer:** 4 (Layer 4 — Lint & Code Standards)
- **Default severity:** `warning`
- **Meaning:** duplicated step block across jobs.
- **Disabling:** Set `YEET-W414: off` in `.yeet/lint.yml` to silence it, or `YEET-W414: error` to make it blocking.

---

## Internal — bugs in yeet itself

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-E900`](#yeet-e900) | `error` | internal error in yeet itself |

---

### `YEET-E900` — internal error in yeet itself

- **Layer:** 9 (Internal — bugs in yeet itself)
- **Default severity:** `error`
- **Meaning:** internal error in yeet itself.
- **Disabling:** Not configurable — this reports a fault in yeet, not in your workflow.

---
