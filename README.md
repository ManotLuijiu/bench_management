# Bench Management

A Frappe app that adds `bench selective-update` — a smarter replacement for
`bench update --reset` when you have apps with expired PATs, mixed remotes,
or apps that should never be reset.

**Inspired by [bench-stop](https://github.com/proenterprise/bench-stop).**

---

## How it works

| App has `upstream` remote | → `git fetch upstream && git reset --hard` | core apps |
|---|---|---|
| App has only `origin` | → `git pull origin <branch>` | your custom apps |
| Listed in `~/.bench_management.json` skip | → skipped entirely | expired PAT, frozen |

**No app names are hardcoded in this repo.** Everything is auto-detected from
git remotes. Per-server overrides (skip list, force overrides) live in
`~/.bench_management.json` on each server — never committed.

---

## Installation

```bash
cd ~/frappe-bench
bench get-app https://github.com/your-org/bench_management
bench install-app bench_management
```

---

## Usage

```bash
# Full update: pull/reset all apps, then migrate + build + restart
bench selective-update

# Preview only — no changes made
bench selective-update --dry-run

# Skip asset build (faster, migrations only)
bench selective-update --skip-build

# Skip both migrate and build (just pull code)
bench selective-update --no-migrate --skip-build
```

---

## Per-server config

Create `~/.bench_management.json` on each server to control app behaviour.
This file is **never committed** — it's personal to each server.

```json
{
  "skip": [
    "some_app_with_expired_pat",
    "another_frozen_app"
  ],
  "force_reset": [],
  "force_pull": []
}
```

| Key | Description |
|---|---|
| `skip` | Apps to skip entirely (expired PAT, broken remote, intentionally frozen) |
| `force_reset` | Override auto-detection → always reset (even if no `upstream` remote) |
| `force_pull` | Override auto-detection → always pull (even if `upstream` remote exists) |

---

## License

MIT
