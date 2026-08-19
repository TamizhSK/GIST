# Secrets, locally

> **The one thing to know first:** GitHub's repository secrets are **write-only**.
> You can set one and you can replace one, but nothing can ever read a value back
> out — not the API, not `gh`, not you, and not yeet. So a local runner cannot
> "sync" them, and any tool that claims to is doing something else.
>
> Running a workflow on your own machine therefore needs a **local copy** of each
> secret, in one of the two places below.

---

## Why GitHub can't give them back

When you paste a value into **Settings → Secrets and variables → Actions**,
GitHub seals it with the repository's public key. The private half lives in
GitHub's infrastructure and the value is only ever unsealed inside a
GitHub-hosted runner, at the moment a workflow asks for it.

The REST API reflects that exactly. `GET /repos/{owner}/{repo}/actions/secrets`
returns this shape:

```json
{ "name": "NPM_TOKEN", "created_at": "…", "updated_at": "…" }
```

There is no `value` field. There is no endpoint that has one. `gh secret list`
prints names because names are all that exist to print.

**What this means in practice:** the value has to come from wherever it was
issued in the first place — the provider's dashboard, your password manager, or
a fresh token you mint for local use. It does not come from GitHub, and it never
did; whoever set it on GitHub had it from that same place.

> A local token should usually be **narrower** than the CI one: read-only, short
> expiry, and scoped to the one repository. It is sitting on a laptop, not in a
> hardened runner.

---

## The two places yeet reads

Both live in the project directory, next to the workflows they belong to — so
one checkout has one set of secrets and two checkouts of two projects never see
each other's.

| | `.yeet/.secrets` | `.env` |
|---|---|---|
| Written by | `yeet secrets set NAME` | you, or `yeet secrets import` |
| On disk | **encrypted** — Fernet (AES-128-CBC + HMAC), key from a passphrase via scrypt | plain text |
| Good for | a token you keep | a value you are trying out, or one CI also injects |
| Precedence | **higher** | lower |
| Prompts | for the passphrase, once, unless it is in your keyring | never |

Highest precedence of all is `--secret NAME=value` on the command line, which
overrides both and is not written anywhere.

```
--secret NAME=value   >   .yeet/.secrets   >   .env
```

### Encrypted: `yeet secrets set`

> **You do not create anything by hand.** `.yeet/.secrets` is a **file**, not a
> folder — one encrypted JSON blob — and `yeet secrets set` creates it, and the
> `.yeet/` directory around it, the first time you run it. There is no
> `mkdir .yeet/.secrets`; making a *directory* of that name is the one thing
> that will stop it working.

```console
$ yeet secrets set NPM_TOKEN
Enter secret value for NPM_TOKEN: ********
Passphrase for .yeet/.secrets: ********
Saved the passphrase to your OS keyring.
Secret 'NPM_TOKEN' stored (encrypted).
```

Run it from the project root — the same directory you point `yeet run` at.
That is the whole configuration step:

```
your-project/
├── .yeet/
│   ├── flows/main.yml     <- the workflow that says ${{ secrets.NPM_TOKEN }}
│   └── .secrets           <- created by `yeet secrets set`  (encrypted, gitignored)
├── .env                   <- or here, in plain text        (gitignored)
└── ...your code
```

The value never appears in a shell argument, so it never reaches your shell
history. The store is one encrypted file at `.yeet/.secrets`.

The passphrase is found in this order, none of which prompt during a run:

1. `$YEET_PASSPHRASE`,
2. your OS keyring, if `keyring` is installed (`pip install keyring` — yeet then
   offers to remember the passphrase the first time you are asked for it),
3. otherwise `yeet secrets set` / `list` / `rm` prompt for it interactively.

`yeet run` with a locked store is **not** fatal: it says so and continues with
`--secret` and `.env` only, because most workflows need no secrets at all.

```console
$ yeet secrets list          # names only — a value is never printed
$ yeet secrets rm NPM_TOKEN
```

### Plain text: `.env`

An ordinary `KEY=value` file in the project root. `export KEY=value` and quoted
values both work.

```dotenv
NPM_TOKEN=npm_xxxxxxxxxxxx
AWS_REGION=eu-west-1
```

Use it when the value is not really a secret (`AWS_REGION` is a *variable*), or
when something else on your machine already writes that file.

**`.env` is plain text and `.yeet/` is bind-mounted into every container.**
`yeet init` puts both `.env` and `.yeet/.secrets` in `.gitignore`; if your
project predates that, check it yourself before the next commit.

---

## The workflow tells you which ones you need

The names are the one part that *is* knowable, because they are written in the
workflow file. `yeet secrets import` reads every `${{ secrets.X }}` and
`${{ vars.Y }}` in your flows and writes the names to `.env` for you:

```console
$ yeet secrets import
  + AWS_REGION   (variable)
  = NPM_TOKEN    (secret)  → from your environment
  + SENTRY_DSN   (secret)  set on GitHub (value not readable)

wrote 3 entries to .env
2 still need a value — edit .env, or `yeet secrets set <NAME>` to keep it encrypted instead.
The values cannot be fetched from GitHub: repository secrets are write-only, so not
even `gh` can read one back. Copy each one from wherever it was issued.
```

Read the three markers as:

* `=` — already filled in, from a variable your shell exports,
* `+ … set on GitHub` — the name exists upstream, so your workflow is correct and
  only the value is missing here. This line appears when the checkout has a
  GitHub remote and `gh` is logged in; the name comes from `gh secret list`, and
  no value is requested, because none can be,
* `+` with nothing after it — nobody has set this anywhere. Often a typo in the
  workflow, worth checking before you go hunting for a token.

Existing entries are never overwritten, so it is safe to re-run whenever someone
adds a workflow. `--dry-run` reports without writing.

**None of this requires a GitHub remote.** A project that has never been pushed
anywhere works exactly the same; you just do not get the "set on GitHub" line.

---

## How the YAML picks it up

The workflow file never names a path. It asks for a secret by NAME, and yeet
resolves that name out of the pool it built from `.yeet/.secrets`, `.env` and
`--secret`:

```yaml
jobs:
  publish:
    runs-on: ubuntu-latest
    steps:
      - run: npm publish
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}   # <- the name, not a path
          AWS_REGION: ${{ vars.AWS_REGION }}
```

`${{ secrets.NPM_TOKEN }}` is resolved before the step runs and the value is
put in that step's environment, so `$NODE_AUTH_TOKEN` inside the container is
the real token. This is byte-for-byte the same file GitHub runs — you do not
write anything yeet-specific to make local secrets work, which is the point.

Reading it straight from the environment works too, and is what a hand-written
`git clone` needs:

```yaml
      - run: echo "$NPM_TOKEN" | docker login -u me --password-stdin
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

Whole run, end to end:

```console
$ cd your-project
$ yeet secrets set NPM_TOKEN     # once. creates .yeet/.secrets
$ yeet check                     # names resolve? E307 if not
$ yeet run                       # the value reaches the container, masked in the log
```

## What happens at run time

```
.env  ─┐
        ├─▶  one pool  ─┬─▶  ${{ secrets.X }}  ─▶  masked in the log and in .yeet/runs/
.secrets┘               └─▶  ${{ vars.Y }}     ─▶  not masked
--secret ┘
```

The workflow file decides which half is which — `secrets.X` and `vars.Y` are
read out of the flow, not out of the store. That matters twice: only the secret
half is redacted (masking `vars.NODE_ENV=production` would replace every
occurrence of "production" in your log), and only the secret half is checked by
**E307**.

Masking covers the raw value *and* its base64 and URL-encoded forms, so a token
stays redacted when some tool prints it inside a URL or a basic-auth header.

### E307 — `secrets.X` is not set

```
YEET-E307: `secrets.NPM_TOKEN` is not set
  fix: `yeet secrets set NPM_TOKEN` stores it encrypted in .yeet/.secrets;
       or add a `NPM_TOKEN=...` line to .env in the project root.
  note: secrets available locally: AWS_REGION. GitHub repository secrets are
        write-only — their values cannot be read back by anything, so running
        this workflow here needs a local copy.
```

This is an **error**, and it stops the run before a container is created. That
is deliberate: an unset secret otherwise surfaces as an empty string somewhere
in the middle of a ten-minute build, in a tool that reports it as something
else entirely.

---

## `GITHUB_TOKEN` is the exception

You never set this one on GitHub — GitHub injects it. Locally, yeet finds one
for you, in this order:

1. `GITHUB_TOKEN` / `GH_TOKEN` / `GITHUB_PAT` in `.yeet/.secrets` or `.env`,
2. the same names in your shell environment,
3. `gh auth token` — if you have ever run `gh auth login`, this already works,
4. your own git credential helper (macOS keychain, `libsecret`, Git Credential
   Manager), asked exactly the way git asks it.

Whatever it finds is added to the mask and passed into every container, which is
what makes a hand-written `git clone https://github.com/…` work in there. A
container is a fresh machine with none of your credentials, so without this it
fails with:

```
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/you/thing.git/'
```

`yeet run -v` says which source it used. Set `YEET_NO_GIT_CREDENTIALS=1` to
inject nothing, if you are reproducing a failure that only happens without a
token.

It is a **project** secret first and a **machine** one second: a token you set
with `yeet secrets set GITHUB_TOKEN` in this repository wins over whatever `gh`
happens to be logged in as, so a workflow cannot silently run as the wrong
account.

---

## Never commit any of this

`yeet check` runs **W404** over your workflow files and flags a literal that
looks like a credential, so a token pasted into a `run:` step is caught before
it is pushed. That rule cannot see `.env`, so:

```gitignore
.env
.env.*
!.env.example
.yeet/.secrets
```

`.yeet/.secrets` has **no trailing slash** — it is a file, and a gitignore
pattern ending in `/` matches directories only and would silently match nothing.

Commit a `.env.example` with the names and no values. It is the fastest possible
onboarding for the next person, and it is the same list `yeet secrets import`
would generate for them.
