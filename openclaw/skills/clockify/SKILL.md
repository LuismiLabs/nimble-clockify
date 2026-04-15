---
name: clockify
description: Log weekly hours to Clockify. Handles the full flow — check pending days, interpret what the user worked on, preview, confirm, and upload.
---

# clockify — Weekly hours skill

**Script:** `clockify-auto.py` (in this repo — set `CLOCKIFY_SCRIPT_PATH` to its absolute path)  
**Working dir:** the repo root (where `.env` lives)  
**Config:** set via `.env` (project, tag, timezone, hours — see `.env.example`)

> **Setup:** Before using this skill, update the path placeholders below with the actual
> absolute path to your local clone of this repo, e.g. `/home/you/nimble-clockify`.

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

### Step 2 — Ask for description (if not already provided)

If the user already said what they worked on in the same message, skip this step.

If unsure what to say, suggest: "Did you work on the same thing all week, or different things on different days?"

**Accepted input formats:**
- `"Worked on X"` → same description for all days
- `"Whole week on X"` → same description
- `"Mon–Wed on X, Thu–Fri on Y"` → per-range
- `"Only Mon and Tue on X, rest on Y"` → per-range

### Step 3 — Build the command and preview

**Simple case** (same description for all days):
```
cd /path/to/nimble-clockify && python3 clockify-auto.py preview --desc "description here"
```

**Multi-range case** (build JSON with date ranges):

The `--entries` JSON is an array where each element has:
- `"from"`: date YYYY-MM-DD (first day of range)
- `"to"`: date YYYY-MM-DD (last day of range)
- `"desc"`: description for those days

Example: "Mon–Wed on bug fixes, Thu–Fri on features"
```
cd /path/to/nimble-clockify && python3 clockify-auto.py preview --entries '[{"from":"2026-04-14","to":"2026-04-16","desc":"Bug fixes"},{"from":"2026-04-17","to":"2026-04-18","desc":"Feature development"}]'
```

**Note:** Ranges in `--entries` must cover ALL pending days — the script reports an error if any day is missing a description.

### Step 4 — Show preview and ask for confirmation

Present the preview output clearly. Something like:

> Hours will look like this:
> - Monday 04/14 → Bug fixes
> - Tuesday 04/15 → Bug fixes
> - ...
> Total: X days · Y.YY hours
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

Show the final confirmation with the total hours created.

---

## Important notes

- **Never create without confirmation.** Always: preview → approval → create.
- If the script fails (API error, tag not found, etc.), show the exact error message.
- **Argentina public holidays** are detected automatically and logged with the "Vacation/Holiday" tag.
- The date range is always: (last day with entries + 1) → this week's Friday.
- If the user says "I didn't work on Tuesday", there is no way to skip individual days — all pending days are created. Clarify this if it comes up.
- The script reads `.env` from the project directory. If the API key fails, check that file.

---

## Automated weekly reminder

The agent checks this during Friday afternoon or Monday morning heartbeats:

1. Run `clockify-auto.py status`
2. If there are pending days, send a message:
   > "Hey, you have [N] unlogged days in Clockify ([start date] → [end date]). What did you work on?"
3. Save `"clockify_last_prompt"` timestamp in `memory/heartbeat-state.json` to avoid asking twice.
4. When the user replies, activate this skill starting at Step 2.
