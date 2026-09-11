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
| **Sales & Proposals** | Drafting and reviewing proposals, SOWs, and contracts. |
| **Idle** | Bench time — no active project, between engagements. |
| **PTO** | Paid time off. **Requires a tag:** Vacation, Holiday, or Personal (includes sick days). Must be HR-authorized first. |
| **UTO** | Unpaid time off. No tag needed. Must be HR-authorized first. |

### Nimble — Fast Foundation activities

These apply only to Nimble's internal Fast Foundation work, never to client-billable engagements:

| Activity | What it covers |
|----------|----------------|
| **Fast Foundation - Custom Dev** | Hands-on custom development within the monthly pre-allocated hours; default for Fast Foundation development. |
| **Fast Foundation - Custom Dev - Authorized Over Budget** | Custom development explicitly approved to exceed the monthly allocation; requires prior client authorization. |
| **Fast Foundation - Reporting** | Progress reports, documentation, and status updates for Fast Foundation. |
| **Fast Foundation - Upgrade Cycle** | Scheduled upgrade and maintenance work included in the service. |

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

The script auto-sets **Activity: PTO** + **Tag: Holiday** + holiday description.

---

## Clockify structure: Client → Project → Activity

In Clockify, **Activities** are **Tasks** under a Project (under a Client). Example for NexStar:

```
CLIENT: NEXSTAR MEDIA INC
  PROJECT: NexStar
    ACTIVITY: Meetings
    ACTIVITY: Other
    ACTIVITY: Working Time
```

Configure in `.env`:
```env
CLOCKIFY_CLIENT_NAME=Nexstar Media Inc
CLOCKIFY_PROJECT_NAME=NexStar
CLOCKIFY_ACTIVITY_NAME=Working Time
CLOCKIFY_PTO_ACTIVITY_NAME=PTO
```

Run **discover** to list the user's actual hierarchy and tags:
```
cd /path/to/nimble-clockify && python3 clockify-auto.py discover
```

---

## Automatic tag guessing

The script and agent **infer tags from context** — no need to ask the user for a tag on normal workdays.

| Situation | Tag (auto) | Activity (auto) |
|-----------|------------|-----------------|
| Normal client work | *(none)* | Working Time |
| User mentions meetings / standup / demo | *(none)* | Meetings |
| User mentions "other" / misc admin | *(none)* | Other |
| Argentina public holiday | **Holiday** | PTO |
| User says vacation / PTO / day off | **Vacation** | PTO |
| User says sick / doctor / personal day | **Personal** | PTO |
| User says overtime / extra hours (authorized) | **Additional Work (Authorized Overtime)** | Working Time (or as specified) |

**Agent rules for tag guessing:**
1. Parse the user's message for keywords before building `--entries`.
2. If unsure between Vacation vs Personal, **ask**: "Was that vacation or a sick/personal day?"
3. Never add a tag on regular work entries unless overtime is mentioned.
4. You can override in `--entries` with explicit `"tag"` and `"activity"` fields.

**Keyword hints:**
- Vacation: `vacation`, `vacaciones`, `pto`, `day off`, `annual leave`
- Personal: `sick`, `doctor`, `medical`, `personal day`, `family`
- Overtime: `overtime`, `extra hours`, `authorized overtime`
- Meetings: `meeting`, `standup`, `demo`, `call`, `sync`, `retro`

---

## What this script automates

| Automated | Still manual / agent judgment |
|-----------|------------------------------|
| Client + Project from `.env` | Multiple clients same day |
| Activity (task) inferred from description | Splitting one day into multiple entries |
| Tag inferred for PTO/holidays/overtime | UTO / Idle (HR-authorized) |
| Argentina holidays → PTO + Holiday | Second client entries |
| Preview shows activity + tag per day | Complex weeks with mixed activities per day |

If the week is complex, use `--entries` with explicit `"activity"` and `"tag"` per range, or tell the user which days need manual Clockify entries.

---

## When to activate this skill

Activate when the user says things like:
- "log my hours", "upload hours to Clockify", "clockify", "log hours"
- "I worked on X this week", "whole week on X"
- "Mon–Wed I did X, Thu–Fri Y"
- When the weekly automated reminder triggers (see `HEARTBEAT.md`)

---

## Full flow (always follow this order)

### Step 0 — Discover structure (first time or if config errors)

If `.env` is new, tags are missing, or project/activity lookup fails:
```
cd /path/to/nimble-clockify && python3 clockify-auto.py discover
```

Show the user their Client → Project → Activity tree and confirm all 4 Nimble tags exist. Update `.env` with the correct `CLOCKIFY_CLIENT_NAME`, `CLOCKIFY_PROJECT_NAME`, and `CLOCKIFY_ACTIVITY_NAME`.

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

**Always use `--verbose` on preview** so the user can verify client, project, activity (`taskId`), tag, and the exact API payload before creating.

**Simple case** (same description for all workdays):
```
cd /path/to/nimble-clockify && python3 clockify-auto.py preview --desc "NexStar — widget refactor" --verbose
```

Each day in verbose preview shows:
```
  Wednesday 2026-06-10
    client:      Nexstar Media Inc
    project:     NexStar (id: ...)
    activity:    Working Time (taskId: ...)
    tag:         (none)
    description: NexStar — widget refactor
    time:        2026-06-10 08:00 → 2026-06-10 16:00 (America/Bogota)
    API payload:
    { "projectId": "...", "taskId": "...", "description": "...", ... }
```

If `taskId: MISSING` appears, run `discover` and fix `.env` or override `project`/`activity` in the plan file (see below).

**Multi-range case** (build JSON with date ranges):

The `--entries` JSON is an array where each element has:
- `"from"`: date YYYY-MM-DD (first day of range)
- `"to"`: date YYYY-MM-DD (last day of range)
- `"desc"`: description for those days
- `"activity"`: optional — `Working Time`, `Meetings`, `Other`, `PTO` (auto-guessed if omitted)
- `"tag"`: optional — `Vacation`, `Holiday`, `Personal`, `Additional Work (Authorized Overtime)` (auto-guessed if omitted)

Example: "Mon–Wed on bug fixes, Thu was meetings, Fri overtime"
```
cd /path/to/nimble-clockify && python3 clockify-auto.py preview --entries '[{"from":"2026-06-09","to":"2026-06-11","desc":"Bug fixes — NexStar"},{"from":"2026-06-12","to":"2026-06-12","desc":"Client standup and planning","activity":"Meetings"},{"from":"2026-06-13","to":"2026-06-13","desc":"Authorized overtime — release fix","tag":"Additional Work (Authorized Overtime)"}]'
```

**Note:** Ranges in `--entries` must cover ALL pending **work** days. Argentina holidays are handled automatically and do not need a description in `--entries`.

### Step 3b — Editable week plan (when days need different activities/tags)

When the user wants to tweak individual days (e.g. Thu = Meetings, Fri = Other), export a plan, let them edit it, then preview again:

```
cd /path/to/nimble-clockify && python3 clockify-auto.py plan --desc "NexStar — widget refactor" -o week-plan.json
```

The user (or agent) edits `week-plan.json`. Each day supports:

| Field | Example values |
|-------|----------------|
| `desc` | `"Client standup and planning"` |
| `activity` | `Working Time`, `Meetings`, `Other`, `PTO` |
| `tag` | `null`, `Vacation`, `Holiday`, `Personal`, `Additional Work (Authorized Overtime)` |
| `project` | `NexStar` (override if needed) |
| `client` | `Nexstar Media Inc` (override if needed) |

Then dry-run from the edited file:
```
cd /path/to/nimble-clockify && python3 clockify-auto.py preview --plan-file week-plan.json --verbose
```

Create after approval:
```
cd /path/to/nimble-clockify && python3 clockify-auto.py create --plan-file week-plan.json
```

**CLI equivalent** (`main.py`):
```
python main.py --plan --from 2026-06-10 --to 2026-06-12 --desc "..." -o week-plan.json
python main.py --from 2026-06-10 --to 2026-06-12 --plan-file week-plan.json --dry-run --verbose
python main.py --from 2026-06-10 --to 2026-06-12 --plan-file week-plan.json
```

### Step 4 — Show preview and ask for confirmation

Present the **verbose preview output** clearly. Include per-day client, project, activity, tag, and flag any `taskId: MISSING` or `⚠️` warnings.

> **Preview — Clockify (dry run)**
>
> | Day | Client / Project | Activity | Tag | Description |
> |-----|------------------|----------|-----|-------------|
> | Wed 06/10 | Nexstar Media Inc / NexStar | Working Time | — | Bug fixes — NexStar |
> | Thu 06/11 | Nexstar Media Inc / NexStar | Meetings | — | Client standup |
> | Fri 06/12 | Nexstar Media Inc / NexStar | Working Time | — | Release fix |
>
> Total: X days · Y.YY hours
>
> ⚠️ If you had meetings, Other activity, PTO/UTO, Idle, or a second client — those need separate entries in Clockify.
>
> Approve?

Wait for the user's response. If they say yes (any variant: "yes", "ok", "approve", "looks good", "👍"):

### Step 5 — Create entries

Replace `preview` with `create` using the **same arguments** (including `--plan-file` if used):
```
cd /path/to/nimble-clockify && python3 clockify-auto.py create --desc "..."
# or
cd /path/to/nimble-clockify && python3 clockify-auto.py create --entries '[...]'
# or
cd /path/to/nimble-clockify && python3 clockify-auto.py create --plan-file week-plan.json
```

Show the final confirmation with total hours created.

Remind the user to verify in Clockify that every weekday is covered and activities/tags look correct in the preview output.

---

## Important notes

- **Never create without confirmation.** Always: preview → approval → create.
- If the script fails (API error, tag not found, activity not found), run `discover` and fix `.env`.
- **Argentina public holidays** → Activity PTO + Tag Holiday (auto).
- **Work entries** → no tag unless overtime is detected.
- **Always preview with `--verbose`** — shows client, project, activity (`taskId`), tag, and full API JSON per day.
- Use `plan` → edit `week-plan.json` → `preview --plan-file --verbose` when days need different activities/tags.
- PTO lives on a different project for some users (e.g. Nimble `Internal`); set `CLOCKIFY_PTO_PROJECT_NAME` in `.env` if holidays show `taskId: MISSING` for PTO.
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
