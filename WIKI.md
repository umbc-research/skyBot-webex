# SkyBot WebEx — Developer Wiki

UMBC Observatory bot for WebEx. Manages observing session spaces, weather checks, and shift scheduling.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [How Messages Flow](#2-how-messages-flow)
3. [Scheduled Jobs](#3-scheduled-jobs)
4. [Session Lifecycle](#4-session-lifecycle)
5. [Session State Persistence](#5-session-state-persistence)
6. [Commands Reference](#6-commands-reference)
7. [Authorization](#7-authorization)
8. [Configuration & Environment](#8-configuration--environment)
9. [Data Files](#9-data-files)
10. [Shared Modules](#10-shared-modules)
11. [Recovery Procedures](#11-recovery-procedures)
12. [WebEx-Specific Quirks](#12-webex-specific-quirks)
13. [Known Gaps vs Discord Bot](#13-known-gaps-vs-discord-bot)

---

## 1. Architecture Overview

```
webex_main.py       — SkyBotWebEx class: all command logic, scheduled tasks, session management
webex_client.py     — Thin wrapper around webexteamssdk (send messages, manage spaces/members)
session_manager.py  — SessionManager: posts to session spaces
                    — SessionStateManager: reads/writes sessions.csv (tracks active sessions)
webhook_server.py   — Flask app: receives incoming WebEx webhook POSTs, routes to bot
WeatherCompiler.py  — Fetches NOAA + ClearOutside data, computes cloud cover forecasts
ScheduleReader.py   — Reads/writes the shift schedule from schedule.csv
htmlParser.py       — Scrapes NOAA and ClearOutside HTML pages
```

**Entry point:** `webex_main.py → main()` starts Flask (blocks main thread) and APScheduler (background thread). The webhook server and scheduler run concurrently.

**Process model:** Single process. Flask serves the webhook endpoint on the main thread; APScheduler runs scheduled jobs on a background thread. No async — everything is synchronous.

**Instance lock:** `main()` calls `_acquire_instance_lock()` which binds a loopback socket on port 47382. If a second instance tries to start, it fails to bind and exits immediately. This prevents double-posting from concurrent scheduler runs (e.g. if the bot is started twice without stopping the first).

---

## 2. How Messages Flow

```
WebEx cloud
  │  POST /webhook  (message created event)
  ▼
webhook_server.py → webhook_handler()
  │  1. Validates resource == 'messages' and event == 'created'
  │  2. Ignores messages from the bot itself (checks personId vs bot_id)
  │  3. Fetches full message text via get_message(message_id)
  │     (WebEx webhook only sends IDs, not content)
  │  4. Extracts: room_id, person_email, message_id, parentId
  ▼
webex_main.py → SkyBotWebEx.handle_message()
  │  1. Strips "skybot " prefix if present
  │  2. Bare "skybot" → treated as "help"
  │  3. Dispatches to _cmd_* method based on command text
  ▼
_cmd_* method → WebExClient.send_message() → WebEx API
```

**Threading note:** `parentId` is passed through the whole chain. When the bot is mentioned inside a session space (which is itself a top-level room), `parentId` is None and `room_id` is the session space ID. The bot uses `room_id` to identify which session space a command came from.

---

## 3. Scheduled Jobs

Both jobs run via APScheduler `BackgroundScheduler` with `CronTrigger`. Times are **UTC**.

### daily_check — 12:05 UTC every day

1. Calls `state.shift_sessions()` — slides the 4-slot state window left (yesterday falls off, slot 4 becomes empty).
2. For each of days 1, 2, 3: calls `_check_session(day, wc)`.
3. Writes updated state to `sessions.csv`.
4. Posts a 3-line GO/Looks bad/Cancelled summary to `WEBEX_OBSERVING_SESSIONS_SPACE_ID`.

**`_check_session(day, wc)` logic:**
```
If no session space exists for this day:
    If weather is clear AND not manually cancelled → create session space
    Else → mark is_clear=False (no space created)
If session space already exists:
    If not cancelled → post weather update inside the space
    If still clear → post Status: GO + observing hours
    If now cloudy → post "Looks bad"
```

### obs_sess_check — 15:05 UTC every day

Checks only **day 1** (tonight).

```
If today's session is marked clear AND a space exists:
    Post weather update (ccForecast) inside the session space
    If still clear → post observing hours
    If now cloudy → post Status: CANCELLED inside space, mark is_cancelled=True
Write sessions.csv
```

**Note:** The 15:05 check can cancel but cannot create — it only acts if a session space already exists.

---

## 4. Session Lifecycle

### Creation (automatic)
1. `daily_check` runs at 12:05.
2. `WeatherCompiler.ccAverage(day)` returns a boolean array; index 0 is True if there is a ≥4-consecutive-hour block with <30% cloud cover.
3. If clear: `_create_session_thread(day, wc)` is called.
   - Looks up today's shift schedule via `ScheduleReader.getSchedule(weekday)`.
   - Builds operator message with `<@personEmail:x@umbc.edu>` mentions.
   - Creates a new WebEx Space titled `Obs Ses YYYY-MM-DD` inside the UMBC Observatory team.
   - Adds each scheduled operator as a space member.
   - Posts operator assignments + openscope question.
   - Posts initial weather forecast (`ccForecast`).
   - Posts shift roster to `WEBEX_SHIFT_TRADING_SPACE_ID`.
4. `state.set_session_for_day(day, parent_id=space_id, is_clear=True)` stores the space ID.

### Creation (manual)
Command: `create session YYYY-MM-DD` (shifters only).
- Date must be today, tomorrow, or day after (days 1–3).
- Checks that no space already exists for that day.
- Calls same `_create_session_thread` logic as automatic creation.

### Daily update (existing session)
On subsequent `daily_check` runs: if a space already exists and is not cancelled, posts updated weather + GO/Looks bad status inside the space.

### Evening update
`obs_sess_check` at 15:05 re-checks tonight only and posts an updated forecast + observing hours or cancels.

### Cancellation (manual)
Command: `cancel` — must be sent **from inside** the session space (not from the main observing space).

1. `find_day_by_parent_id(room_id)` finds which day this space belongs to.
2. Sets `is_cancelled=True`, `is_clear=False`.
3. Posts Status: CANCELLED inside the session space.
4. Writes `sessions.csv`.

### Cancellation (automatic — weather)
If `obs_sess_check` finds cloud cover too high at 15:05, it calls `post_status_cancelled()` on the session space and sets `is_cancelled=True`.

### Uncancellation
Command: `uncancel` — must be sent from inside the session space.

1. Sets `is_cancelled=False`, `is_clear=True`.
2. Posts "Observing session has been uncancelled." inside the space.
3. Re-posts the current operator schedule (so members can see who's on after any trades).
4. Writes `sessions.csv`.

---

## 5. Session State Persistence

**File:** `data/sessions.csv`

**Format:** 4 rows (one per day slot), columns: `space_id,date,is_clear,is_cancelled`

```
Y2lzY29zcGFyazov...,2026-06-29,1,0   ← day 1 (today)
,2026-06-30,0,0                        ← day 2 (empty space_id = no session)
,2026-07-01,0,0
,2026-07-02,0,0
```

**`SessionStateManager` internals:**
- Three parallel lists of length 4: `session_parent_ids`, `clear_night_list`, `cancelled_night_list`.
- Index 0 = day 1 (tonight), index 1 = day 2, etc.
- `shift_sessions()`: slides everything left by 1, clears index 3. Called at the start of each `daily_check`.
- `get_session_for_day(day)`: returns dict with `parent_id`, `is_clear`, `is_cancelled`, `date`. `day` is 1-indexed.
- `set_session_for_day(day, ...)`: updates only the fields explicitly passed (None = no change).
- `find_day_by_parent_id(space_id)`: returns 1–4 or None. Used by cancel/uncancel to identify which day's session a command came from.

**On startup:** `read_sessions()` loads `sessions.csv`. If the file is missing, creates it with all-empty state.

---

## 6. Commands Reference

### General commands (anyone can use)

| Command | What it does |
|---|---|
| `ping` | Replies with the hostname running the bot |
| `help` | Posts full command reference (markdown formatted) |
| `graph` | Sends the NOAA 48-hour weather forecast image |
| `details` | Posts cloud cover table (18:00–05:00) for next 3 nights |
| `details today` | Same but only tonight |
| `details extended` | Cloud cover 18:00–10:00 (includes morning hours) |
| `popscope` | Posts sunset–21:00 cloud cover for next 3 nights |
| `sessions` | Lists session status (GO/Cancelled/Pending/None) for today + next 3 days |

All general commands work from any space the bot is in.

**`skybot` prefix:** In group spaces, users @mention the bot, which WebEx strips. The bot also explicitly accepts a `skybot` prefix and strips it. Bare `skybot` with no command → `help`.

### Shifter-only commands

Require the sender's email to be in `AUTHORIZED_SHIFTERS`. If not authorized, bot replies with a permission error.

| Command | What it does |
|---|---|
| `create session YYYY-MM-DD` | Manually creates a session space for today/tomorrow/day after |
| `trade YYYY-MM-DD SHIFT new_email` | Trades a shift; updates schedule, space membership, posts announcement |
| `cancel` | Cancels today's session (must be sent from inside the session space) |
| `uncancel` | Uncancels a cancelled session (must be sent from inside the session space) |
| `enable ms` | Enables midnight shift pinging in new session spaces; persists to config.csv |
| `disable ms` | Disables midnight shift pinging; persists to config.csv |
| `schedule DAY SHIFT USERNAME` | Updates the schedule CSV (e.g. `schedule mon ES1 broslin1`) |
| `testcheck` | Manually triggers `daily_check` for testing (remove before production) |

### `trade` command detail

Format: `trade YYYY-MM-DD SHIFT new_email`

Valid shifts: ES1, ES2, MS1, MS2, GS1, GS2. Date must be within the next 3 days and have an existing session space.

Behavior:
1. Verifies sender owns the shift OR is an authorized shifter (mods can trade any shift).
2. Removes old operator from the session space if they have no other shifts that day.
3. Adds new operator to the session space.
4. Posts announcement with @mentions inside the session space.
5. Re-posts the full updated operator schedule in the session space.
6. Confirms the trade in the channel where the command was sent.

### `schedule` command detail

Format: `schedule DAY SHIFT USERNAME`

- DAY: mon/tue/wed/thu/fri/sat/sun (or full name)
- SHIFT: ES1/ES2/MS1/MS2/GS1/GS2
- USERNAME: UMBC username from operators.csv (not email — the short username like `broslin1`)

Rewrites `data/schedule.csv` in-place. Changes take effect immediately for any future session space created that day.

---

## 7. Authorization

**Mechanism:** `AUTHORIZED_SHIFTERS` in `.env` — comma-separated list of UMBC email addresses.

```
AUTHORIZED_SHIFTERS=shifter1@umbc.edu,shifter2@umbc.edu,coordinator@umbc.edu
```

**Check:** `WebExClient.is_authorized(email, allowed_emails)` — case-insensitive comparison, whitespace-trimmed.

**`_check_shifter(email, room_id, parent_id)`:** Called at the top of every shifter command. Sends a permission error and returns False if not authorized; returns True if authorized. The command body only runs if it returns True.

This replaces Discord's role-based system. WebEx has no roles — all spaces are independent, so authorization must be done by email list.

---

## 8. Configuration & Environment

**File:** `.env` (copy from `.env.example` for a fresh deployment)

| Variable | Purpose |
|---|---|
| `WEBEX_BOT_TOKEN` | Bot access token from developer.webex.com |
| `WEBEX_OBSERVING_SPACE_ID` | Main space where operators send commands to the bot |
| `WEBEX_OBSERVING_SESSIONS_SPACE_ID` | Space where daily check GO/Looks bad/Cancelled summaries are posted |
| `WEBEX_SHIFT_TRADING_SPACE_ID` | Space where shift rosters are posted when a session space is created |
| `WEBHOOK_URL` | Public HTTPS base URL (e.g. ngrok URL); bot registers `{WEBHOOK_URL}/webhook` with WebEx |
| `FLASK_PORT` | Port Flask listens on (default: 8080) |
| `AUTHORIZED_SHIFTERS` | Comma-separated emails of mods/shift leads who can use restricted commands |
| `SCHEDULE_COORDINATOR_EMAIL` | Email of schedule coordinator (default: coordinator@umbc.edu) |
| `DST_ACTIVE` | `True`/`False` — adjusts sunrise/sunset calculations for DST (default: True) |

**Runtime config file:** `data/config.csv`

Single key-value used to persist the midnight shift toggle across restarts:
```
midnight_shifts_enabled,0
```
Read on startup by `_read_config()`. Written by `enable ms` / `disable ms` commands via `_write_config()`.

---

## 9. Data Files

All in `data/`.

### `sessions.csv`
Tracks active session spaces. 4 rows × 4 columns: `space_id,date,is_clear,is_cancelled`. Written after every state change. See [Section 5](#5-session-state-persistence).

### `schedule.csv`
7 days × 6 shifts = 42 data rows, separated by day-header rows.

Format per day:
```
Monday
username1,email1@umbc.edu
username2,email2@umbc.edu
...  (6 shift rows: ES1, ES2, MS1, MS2, GS1, GS2)
```

If a shift is unassigned, the email column contains `1`.

Read by `ScheduleReader.readScheduleFile()` on bot startup. Modified by the `schedule` command.

### `operators.csv`
Maps UMBC usernames to emails. One row per operator: `username,email@umbc.edu`.

Used by `ScheduleReader.readOperatorFile()` when the `schedule` command runs, to validate that a username exists.

### `config.csv`
See [Section 8](#8-configuration--environment).

---

## 10. Shared Modules

These live in the parent directory (`C:\Users\Proxi\skyBot\`) and are also copied into `skybot-webex/`. The bot imports from the parent via `sys.path.insert(0, PARENT_DIR)`.

### `WeatherCompiler.py`

Instantiated fresh per use (`wc = WeatherCompiler()`) — each instantiation fetches live data from NOAA and ClearOutside.

Key methods:
- `ccAverage(day)` — Returns a boolean array. Index 0 = True if there is a ≥4-consecutive-hour clear block (cloud cover <30%) from sunset to sunrise. Used to decide GO/no-GO.
- `ccForecast(day, extended)` — Returns a formatted markdown code block table of cloud cover by hour (NOAA + ClearOutside + temperature). `extended=True` adds 05:00–10:00 morning hours.
- `popScopeCheck(day)` — Like ccAverage but for the sunset-to-21:00 window at <50% threshold.
- `popScopeForecast(day)` — Formatted table for sunset to 21:00.
- `sunriseTime(date)` / `sunsetTime(date)` — Returns datetime. Used for observing window calculations.
- `getSunrise(day)` / `getSunset(day)` — Returns hour int, DST-adjusted.

**Performance note:** Each `WeatherCompiler()` instantiation makes 5 HTTP requests (3 NOAA pages + 1 ClearOutside + 1 temp page). Creating it once per scheduled job (not per command) is intentional.

### `ScheduleReader.py`

- `readScheduleFile()` — Loads `schedule.csv` into `self.schedule[day][shift]` = `[username, email]`. Must be called with CWD set to the `data/` directory.
- `getSchedule(weekday)` — Returns the 6-shift list for a given weekday (0=Monday).
- `changeSchedule(command)` — Parses a `skybot schedule ...` string, validates, rewrites `schedule.csv`.
- `readOperatorFile()` — Loads `operators.csv` into `self.operators` dict. Called lazily on first `changeSchedule`.

**CWD dependency:** Both file reads use bare `open("schedule.csv")` and `open("operators.csv")` — no path prefixes. The bot manually `os.chdir()`s to `data/` before calling these and restores CWD afterward.

### `htmlParser.py`

Scrapes NOAA digital forecast pages and ClearOutside. Called internally by `WeatherCompiler.__init__()`. Not called directly by the bot.

---

## 11. Recovery Procedures

### Bot restarted / sessions.csv out of sync

**Symptom:** Bot starts up but `sessions.csv` has wrong or stale space IDs, or an empty file.

**Fix options:**
1. Manually edit `sessions.csv`. Format: `space_id,YYYY-MM-DD,is_clear(1/0),is_cancelled(1/0)`. Find the correct space ID from the WebEx app (open the session space → get the space ID from the URL or via `list_spaces.py`).
2. Use `create session YYYY-MM-DD` to create a fresh session space for the affected date (loses the old space but creates a new correct one).

**Note:** There is currently no `link session` command to re-link to an existing space without editing the CSV manually. This is a known gap — see TODO.

### Wrong space IDs in .env

Run `list_spaces.py` (standalone utility in `skybot-webex/`) to list all spaces and teams the bot is currently a member of. Update `.env` accordingly.

### Webhook stopped working (ngrok restarted)

1. Get the new ngrok URL.
2. Update `WEBHOOK_URL` in `.env`.
3. Restart the bot — on startup it calls `delete_all_webhooks()` then `create_webhook()` with the new URL automatically.

Alternatively, POST to `/setup-webhook` endpoint on the running bot to re-register without restarting.

### Bot is not receiving messages

Check in order:
1. Is the bot process running? Flask will log incoming POST requests.
2. Is the `WEBHOOK_URL` reachable from the internet? Test by hitting `{WEBHOOK_URL}/health`.
3. Is the webhook registered? The bot prints the webhook ID on startup. If missing, check for a `WEBHOOK_URL not set` warning.
4. Is the bot a member of the space where messages are being sent?

### Session space was created manually (outside the bot)

The bot has no knowledge of manually created spaces. Either:
1. Edit `sessions.csv` directly with the space ID.
2. Use `create session YYYY-MM-DD` inside the observing space to have the bot create its own space (the old manually-created one will be orphaned).

### Midnight shift setting lost after restart

`enable ms` / `disable ms` persist to `data/config.csv`. If the file is missing or corrupt, the bot defaults to `False` (midnight shifts disabled). Re-run the command to restore the setting.

---

## 12. WebEx-Specific Quirks

### @mention format

WebEx mentions are `<@personEmail:user@umbc.edu>` — not a user ID, an email. This is what `WebExClient.mention_person(email)` generates. Works in both markdown and plain text fields of the API.

### Webhook payload doesn't include message text

WebEx only sends event metadata in webhook payloads (IDs, not content). The bot must make a second API call (`get_message(message_id)`) to fetch the actual message text. This adds ~200ms latency per message but is unavoidable.

### Bot ignores its own messages

The bot fetches its own user ID (`me.id`) on startup and skips any webhook event where `personId == bot_id`. This prevents the bot from responding to itself.

### `skybot` prefix stripping

In group spaces, WebEx strips the @mention from the message text before delivering it. So a user sending `@skyBot ping` arrives as `ping`. The bot also handles the prefix explicitly: if the message starts with `skybot ` it strips it, so `skybot ping` and `ping` both work. Bare `skybot` (no command) becomes `help`.

### Session spaces are real spaces, not threads

Unlike Discord (which used forum threads), each observing session gets a full independent WebEx Space. This means:
- The bot must be explicitly added as a moderator/member of the UMBC Observatory team to create spaces within it.
- Space IDs (not message IDs) are stored in `sessions.csv`.
- `cancel` and `uncancel` identify the session by matching `room_id` (where the message was sent) against stored space IDs.

### No role system

WebEx has no role/group mentions. "Operator needed" currently prints as plain text with no ping. All authorization is handled by email lists in `.env`.

---

## 13. Known Gaps vs Discord Bot

The following features exist in the Discord bot (`main.py`) but are not yet implemented in the WebEx version. See `TODO.txt` (Gap Audit section) for full details.

| Feature | Status |
|---|---|
| Popscope automated daily check (12:04) | Not implemented — command exists, scheduler job missing |
| Day-of auto-cancellation in daily_check | Not implemented — WebEx only marks "Looks bad" for day 1 |
| Weekend/Friday auto-cancellation | Not implemented — pending meeting decision |
| Google Calendar integration | Not implemented — architecture TBD |
| Per-shift partial cancellation (ES/MS/GS) | Blocked by calendar integration |
| Weather cancel alert to ops/engineering space | Not implemented — no space configured |
| "Operator needed" group ping | Not implemented — no role system in WebEx |
| obs_sess_check status update to sessions space | Not implemented — only posts inside session space |
| Session re-linking command (`set thread` equiv.) | Not implemented — manual CSV edit required |
| GO/NO-GO report log (report.txt) | Not implemented |
| Email notifications to observatory@umbc.edu | Not implemented |
| Permanent space members on session creation | Not implemented — pending member list |
