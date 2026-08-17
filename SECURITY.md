# Security Policy

## Supported versions

`yeet` is pre-1.0. Fixes land on `main` and in the next tag; there are no
backports to older tags.

## Reporting a vulnerability

Please **do not** open a public issue.

Use GitHub's private reporting — [Security → Report a
vulnerability](https://github.com/TamizhSK/GIST/security/advisories/new) — or
email **tamizhazhagansk@gmail.com** with `yeet security` in the subject.

Include the version (`yeet --version`), the OS, and the smallest workflow file
that reproduces it. We will acknowledge within seven days and tell you whether
we consider it a vulnerability and what the fix looks like.

## What is in scope

`yeet` runs code that a workflow file tells it to run, in a container it
builds. That is its job, so "a workflow can execute commands" is not a
vulnerability. These are:

- **Escaping the workspace.** A cache tarball, an artifact, or a fetched action
  writing outside the directory it was given.
- **Secrets in the clear.** A value from the secret store reaching stdout,
  stderr, the JSONL log, the SARIF output, or a diagnostic — including its
  base64 and URL-encoded forms.
- **Reading the store without the passphrase.** `.yeet/.secrets` is encrypted;
  anything that decrypts it without the key is in scope.
- **The installers.** `install.sh` and `install.ps1` writing outside
  `~/.local` / `%LOCALAPPDATA%`, or requiring elevation to do their job.
- **A mistranslated workflow.** A file that is read as doing something other
  than what it says, where the difference has a security consequence.

## What is not

- Anything requiring an attacker who can already write to your workflow files.
  A `workflows/` directory is executable input by design.
- Vulnerabilities in Docker, in the images a workflow pulls, or in the actions
  it uses. Report those upstream.
- The absence of a sandbox around `runs-on: local`. It runs on your host on
  purpose, and says so.
