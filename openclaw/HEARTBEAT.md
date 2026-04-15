# HEARTBEAT.md — Periodic checks

## Clockify — Weekly hours reminder

**When to check:** Friday after 3 PM (local time) OR Monday before noon.  
**Frequency:** Maximum 1 reminder per week — track with `memory/heartbeat-state.json` key `clockify_last_prompt`.

**Steps:**
1. Read `memory/heartbeat-state.json` — if `clockify_last_prompt` was less than 5 days ago, skip.
2. Run: `cd /path/to/nimble-clockify && python3 clockify-auto.py status`
3. If there are pending days → send a message:
   > "Hey, you have [N] unlogged days in Clockify ([start date] → [end date]). What did you work on?"
4. Update `clockify_last_prompt` with the current timestamp.
5. When the user replies with what they worked on → activate the `clockify` skill (see `skills/clockify/SKILL.md`).
