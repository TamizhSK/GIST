# yeet Diagnostic Rules Reference

*Auto-generated from `src/yeet/core/codes.py` — do not hand-edit.*

This document lists all diagnostic codes emitted by `yeet` during validation and linting.

## Layer 0 — File & Encoding

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-E001`](#yeet-e001) | `error` | file unreadable or missing |
| [`YEET-E002`](#yeet-e002) | `error` | file is empty |
| [`YEET-E003`](#yeet-e003) | `error` | non-UTF-8 character encoding |
| [`YEET-W004`](#yeet-w004) | `warning` | UTF-8 BOM present |
| [`YEET-E005`](#yeet-e005) | `error` | tabs used for indentation |
| [`YEET-W006`](#yeet-w006) | `warning` | CRLF line endings |
| [`YEET-W007`](#yeet-w007) | `warning` | file size exceeds 1 MB |

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

## Layer 2 — Schema Validation

| Code | Default Severity | Title |
|---|---|---|
| [`YEET-E201`](#yeet-e201) | `error` | unknown key |
| [`YEET-E202`](#yeet-e202) | `error` | required key missing |
| [`YEET-E203`](#yeet-e203) | `error` | invalid data type |
| [`YEET-E204`](#yeet-e204) | `error` | step has both `run` and `uses` |
| [`YEET-E205`](#yeet-e205) | `error` | step has neither `run` nor `uses` |
| [`YEET-E206`](#yeet-e206) | `error` | invalid event name |
| [`YEET-E207`](#yeet-e207) | `error` | invalid job id |
| [`YEET-E208`](#yeet-e208) | `error` | empty step list |

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
| [`YEET-E313`](#yeet-e313) | `error` | missing required action input |
| [`YEET-E314`](#yeet-e314) | `error` | unknown action input |
| [`YEET-E315`](#yeet-e315) | `error` | `cooked_on:` could not be resolved to an image |
| [`YEET-E316`](#yeet-e316) | `error` | invalid runner specification |
| [`YEET-W317`](#yeet-w317) | `warning` | deprecated workflow syntax |
| [`YEET-W318`](#yeet-w318) | `warning` | unused output variable |
| [`YEET-W319`](#yeet-w319) | `warning` | action version mismatch |

---

## Layer 4 — Lint & Code Standards

| Code | Default Severity | Title |
|---|---|---|
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
| [`YEET-I415`](#yeet-i415) | `info` | mixed dialect and canonical keys |
