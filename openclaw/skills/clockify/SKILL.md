---
name: clockify
description: Log weekly hours to Clockify following Nimble's June 2026 time tracking rules. Handles status checks, interprets what the user worked on, preview, confirm, and upload.
---

# clockify — Weekly hours skill

**Script:** `clockify-auto.py` (in this repo — set `CLOCKIFY_SCRIPT_PATH` to its absolute path)  
**Working dir:** the repo root (where `.env` lives)  
**Config:** set via `.env` (client/project, tags, timezone, hours — see `.env.example`)

> **Setup:** Before using this skill, update the path placeholders below with the actual
> absolute path to your local clone of this repo, e.g. `/home/you/nimble-clockify`.

---

## Nimble Time Tracking Guide (June 2026)

These rules apply to everyone, every week. The agent must follow them when helping users log hours.

### Core rules (always)

1. **Every weekday must be covered.** Total logged hours each day should match the user's shift. If they didn't work — vacation, sick day, public holiday, bench time — it must still be logged using the correct **Activity** (PTO, UTO, Idle). A day with **no entries is always wrong**.
2. **Log at least once a week.** Hours must be submitted **before the week ends**. Daily logging is better, but the hard minimum is: **no week closes with missing hours**.
3. **One entry per activity, per client.** If the day includes different types of work, use separate entries. If the user worked for two clients the same day, each client gets its own entry with its own Client, Project, and Activity. Do not group unrelated work into one entry.
4. **Add a description.** Not required for most activities, but strongly recommended — one sentence is enough. If the user used the **Other** activity, a description is **mandatory**.

### The four levels

Every entry uses exactly these fields:

| Level | Answers | Example values |
|-------|---------|----------------|
| **Client** | Who is the work for? | Nexstar, Red Bull, Lexipol, Nimble… |
| **Project** | Under which initiative or engagement? | Staffing, Initiative #8, Internal… |
| **Activity** | What type of work was done? | Working Time, Meetings, Other, PTO… |
| **Tag** | Required only for PTO or overtime | Vacation, Holiday, Personal, Additional Work (Authorized Overtime) |

**Rule:** Every entry needs Client + Project + Activity. A Tag is only required for PTO or authorized overtime.

### Activities — shared template (all clients)

| Activity | What it covers |
|----------|----------------|
| **Working Time** | Hands-on client work — development, QA, DevOps, infrastructure, support, PM, onboarding, etc. Default when it's productive client work and not a meeting. |
| **Meetings** | Client calls, standups, demos, synchronous communication. |
| **Other** | Anything that doesn't fit above. **Description required.** |

### Nimble — internal activities only

| Activity | What it covers |
|----------|----------------|
| **Meetings** | Internal syncs, team huddles, all-hands. |
| **R&D** | Research, experimentation, internal tech exploration. |
| **Upskilling** | Training, courses, certifications. |
| **Coaching & Enablement** | Coaching, mentoring, knowledge sharing. |
| **Recruiting & Interviews** | Hiring, screening, technical evaluations. |
| **Idle** | Bench time — no active project, between engagements. |
| **PTO** | Paid time off. **Requires a tag:** Vacation, Holiday, or Personal (includes sick days). Must be HR-authorized first. |
| **UTO** | Unpaid time off. No tag needed. Must be HR-authorized first. |

### Tags (only 4 — most entries have no tag)

| Tag | Type | When to use |
|-----|------|-------------|
| **Vacation** | PTO | Activity: PTO — paid vacation days |
| **Holiday** | PTO | Activity: PTO — national/regional public holidays |
| **Personal** | PTO | Activity: PTO — personal days, includes sick days |
| **Additional Work (Authorized Overtime)** | Contract | Add to any billable entry for authorized overtime |

### Pre-submit checklist

Before creating any entry, confirm:

- [ ] Client selected?
- [ ] Project selected?
- [ ] Activity selected from the template?
- [ ] If PTO → tag added (Vacation / Holiday / Personal)?
- [ ] If overtime → **Additional Work (Authorized Overtime)** tag added?
- [ ] If Activity is **Other** → description written?

### Argentina public holidays

Argentina holidays are detected automatically by the script. Per Nimble rules they should be logged as:

- **Activity:** PTO
- **Tag:** Holiday
- **Description:** e.g. `"Public holiday — Argentina"`

The script maps these to the holiday tag configured in `.env` (`CLOCKIFY_HOLIDAY_TAG_NAME=Holiday`).

---

## What this script automates vs. what the user must set in Clockify

The script handles **bulk weekday logging** for a single Client/Project configured in `.env`:

| Automated by script | User/agent must handle manually or in Clockify |
|---------------------|-----------------------------------------------|
| Detect pending weekdays since last entry | Multiple clients in the same day |
| Argentina holiday detection → Holiday tag | Choosing the correct **Activity** per entry |
| Single description (or per-range descriptions) | Splitting day into multiple entries (meetings vs work) |
| Preview → confirm → create flow | PTO / UTO / Idle days (HR-authorized) |
| Skip days that already have entries | **Other** activity entries (description required) |
| | Overtime tag on authorized extra hours |

If the user's week is more complex than "same client, same activity all week", help them structure separate `--entries` ranges **and** tell them which days may still need manual entries in Clockify for meetings, Other, or a second client.

---

## When to activate this skill

Activate when the user says things like:
- "log my hours", "upload hours to Clockify", "clockify", "log hours"
- "I worked on X this week", "whole week on X"
- "Mon–Wed I did X, Thu–Fri Y"
- When the weekly automated reminder triggers (see `HEARTBEAT.md`)

---

## Full flow (always follow this order)

### Step 1 — Check status

Run:
```
cd /path/to/nimble-clockify && python3 clockify-auto.py status
```

Show the user how many days are pending and the date range.  
If there are no pending days, tell them and stop.

Remind them: **every weekday must have hours before the week ends.**

### Step 2 — Ask what they worked on (if not already provided)

If the user already described their week in the same message, skip to Step 3.

Otherwise ask:

> "What did you work on this week? Same thing all week, or different things on different days?  
> Also — any PTO, sick days, bench time (Idle), or meetings that need a separate entry?"

**Accepted input formats:**
- `"Worked on X"` → same description for all workdays
- `"Whole week on X"` → same description
- `"Mon–Wed on X, Thu–Fri on Y"` → per-range
- `"Tuesday was PTO — sick day"` → **do not** auto-log via script; tell user to log manually in Clockify as Activity PTO + tag Personal (HR-authorized)
- `"Wednesday was a holiday"` → script handles automatically (PTO + Holiday tag)

**Before previewing, confirm:**
- Default activity assumption: **Working Time** (unless they say meetings, Other, PTO, etc.)
- Description present (especially if they mention **Other**)
- Client/Project match their `.env` config

### Step 3 — Build the command and preview

**Simple case** (same description for all workdays):
```
cd /path/to/nimble-clockify && python3 clockify-auto.py preview --desc "NexStar — widget refactor"
```

**Multi-range case** (build JSON with date ranges):

The `--entries` JSON is an array where each element has:
- `"from"`: date YYYY-MM-DD (first day of range)
- `"to"`: date YYYY-MM-DD (last day of range)
- `"desc"`: description for those days

Example: "Mon–Wed on bug fixes, Thu–Fri on features"
```
cd /path/to/nimble-clockify && python3 clockify-auto.py preview --entries '[{"from":"2026-06-09","to":"2026-06-11","desc":"Bug fixes — NexStar"},{"from":"2026-06-12","to":"2026-06-13","desc":"Feature development — NexStar"}]'
```

**Note:** Ranges in `--entries` must cover ALL pending **work** days. Argentina holidays are handled automatically and do not need a description in `--entries`.

### Step 4 — Show preview and ask for confirmation

Present the preview clearly. Include Nimble context:

> **Preview — Clockify**
>
> Client/Project: (from your `.env` config)  
> Default activity assumed: **Working Time** (no tag)
>
> | Day | Description | Notes |
> |-----|-------------|-------|
> | Mon 06/09 | Bug fixes — NexStar | Working Time |
> | Tue 06/10 | Bug fixes — NexStar | Working Time |
> | Wed 06/11 | Public holiday | PTO + Holiday tag |
> | … | … | … |
>
> Total: X days · Y.YY hours
>
> ⚠️ If you had meetings, Other activity, PTO/UTO, Idle, or a second client — those need separate entries in Clockify.
>
> Approve?

Wait for the user's response. If they say yes (any variant: "yes", "ok", "approve", "looks good", "👍"):

### Step 5 — Create entries

Replace `preview` with `create` using the same arguments:
```
cd /path/to/nimble-clockify && python3 clockify-auto.py create --desc "..."
# or
cd /path/to/nimble-clockify && python3 clockify-auto.py create --entries '[...]'
```

Show the final confirmation with total hours created.

Remind the user to verify in Clockify that:
- Activities are correct (script sets description only; Activity may need adjustment in Clockify if not mapped by project)
- Any PTO/UTO/Idle/meeting/overtime days were logged separately
- Every weekday in the week is covered

---

## Important notes

- **Never create without confirmation.** Always: preview → approval → create.
- If the script fails (API error, tag not found, etc.), show the exact error message.
- **Argentina public holidays** → logged with Holiday tag (configure `CLOCKIFY_HOLIDAY_TAG_NAME=Holiday` in `.env`).
- **Work entries** → no tag required per new Nimble rules. Leave `CLOCKIFY_TAG_NAME` empty or unset if your workspace no longer uses work tags.
- Date range is always: (last day with entries + 1) → this week's Friday.
- The script cannot skip individual workdays — all pending days get an entry. If the user didn't work a specific day (PTO/sick/bench), they must log that day manually in Clockify with the correct Activity instead of using this script for that day.
- The script reads `.env` from the project directory. If the API key fails, check that file.
- Edge cases → suggest screenshots to lead, Ops, or HR.

---

## Automated weekly reminder

The agent checks this during **Friday afternoon** or **Monday morning** heartbeats (see `HEARTBEAT.md`):

1. Run `clockify-auto.py status`
2. If there are pending days, send a message:
   > "Hey — you have [N] unlogged weekdays in Clockify ([start] → [end]). Per Nimble policy, every weekday must be covered before the week ends. What did you work on?"
3. Save `"clockify_last_prompt"` timestamp in `memory/heartbeat-state.json` to avoid asking twice.
4. When the user replies, activate this skill starting at Step 2.
