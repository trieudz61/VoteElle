# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A collection of Python scripts that automate ELLE Beauty Awards voting flows.

There are two main subsystems:

1) **Turnstile token producer**: opens many Chromium instances/tabs, solves Cloudflare Turnstile, and pushes tokens into a Supabase table.
2) **Vote workers**: multiple strategies for creating/using accounts to vote, all of which consume Turnstile tokens from Supabase and then call ELLE endpoints.

Supabase is used as shared state:
- `turnstile_tokens` table: pool of fresh tokens.
- `accounts` table: stores created accounts and `cookie_sid` (vote_sid) + `last_time_vote`.
- RPC `pop_token`: vote scripts call this to atomically pop one token from the pool.

## Common commands

### Run the master launcher (recommended)
Runs Turnstile + selected vote scripts concurrently and shows a combined TUI dashboard.

```bash
python3 run_all.py
```

Environment variables used by the launcher:
- `NUM_TABS` (for Turnstile producer)
- `NUM_WORKERS` (for vote scripts)
- `SUPABASE_URL`, `SUPABASE_KEY`

### Run individual scripts

Turnstile token producer (writes to `turnstile_tokens`):
```bash
NUM_TABS=12 python3 Turnstile_MultiWorker.py
```

Vote worker variants (consume tokens via `pop_token`):
```bash
NUM_WORKERS=7 python3 NewWay.py
NUM_WORKERS=15 python3 Reg_Login_Vote.py
NUM_WORKERS=15 python3 Reg_Login_Vote_MMO.py
```

Reuse existing `cookie_sid` to vote without registration/login:
```bash
python3 Vote_SID_Reuse.py
```

Analyze how many accounts will be ready to vote over the next 24h:
```bash
python3 analyze_24h.py
```

### Install dependencies

This repo currently does not include a pinned dependency file (requirements.txt / pyproject.toml).
Based on imports, scripts require at least:
- `requests`, `python-dotenv`, `supabase`
- `rich` (TUI dashboard)
- `DrissionPage` (Turnstile Chromium automation)

If you add a dependency file later, update this section to match.

## High-level architecture

### 1) Turnstile token production
- Entry point: [Turnstile_MultiWorker.py](Turnstile_MultiWorker.py)
- Uses DrissionPage (Chromium + CDP) to render Turnstile widget and harvest tokens.
- Inserts tokens into Supabase `turnstile_tokens`.
- Background cleanup thread deletes tokens older than ~3 minutes and enforces a max pool size.

Key knobs:
- `NUM_TABS`: number of parallel Chromium workers.
- `MAX_POOL`: max number of tokens to keep in DB.

### 2) Vote worker flows
Vote scripts share a common pattern:
1. Pop 1+ Turnstile tokens from Supabase via RPC `pop_token`.
2. Register account on `https://events.elle.vn/register`.
3. Poll an email provider for ELLE confirmation link.
4. Activate account via `https://baseapi.elle.vn/auth/email-confirmation?...`.
5. Login on `https://events.elle.vn/login?...`.
6. Vote by POSTing to `https://events.elle.vn/elle-beauty-awards-2026/nhan-vat` with `next-action` headers.
7. Store `cookie_sid` (`vote_sid`) and timestamps into Supabase `accounts`.

Main variants:
- [Reg_Login_Vote.py](Reg_Login_Vote.py): uses smvmail.com mailbox API.
- [NewWay.py](NewWay.py): uses Gmail variants + Hotmail forwarding, and calls a third-party Hotmail OAuth message API.
- [Reg_Login_Vote_MMO.py](Reg_Login_Vote_MMO.py): uses TempMailMMO API.

### 3) SID reuse voting
- Entry point: [Vote_SID_Reuse.py](Vote_SID_Reuse.py)
- Queries Supabase `accounts` for rows with `cookie_sid` and eligible by cooldown (`last_time_vote` is NULL or older than `COOLDOWN_HOURS`).
- Votes by sending requests with `cookies={'vote_sid': sid}`.
- Only updates `last_time_vote` on success.

### 4) Dashboards / observability
- Worker scripts import [dashboard.py](dashboard.py) to show a per-script TUI.
- When launched via [run_all.py](run_all.py), each script runs with `NO_DASHBOARD=1` and prints plain logs that the master dashboard parses.
- `dashboard.py` also writes per-run logs into `./logs/`.

## Repository entrypoints
- [run_all.py](run_all.py): interactive launcher + master dashboard
- [Turnstile_MultiWorker.py](Turnstile_MultiWorker.py): token producer
- [Reg_Login_Vote.py](Reg_Login_Vote.py), [NewWay.py](NewWay.py), [Reg_Login_Vote_MMO.py](Reg_Login_Vote_MMO.py): voting flows
- [Vote_SID_Reuse.py](Vote_SID_Reuse.py): vote using stored SIDs
- [analyze_24h.py](analyze_24h.py): readiness analysis
