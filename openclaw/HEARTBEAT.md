# HEARTBEAT.md — Periodic checks

## Clockify — Weekly hours reminder

**Policy (Nimble, June 2026):** Every weekday must have hours logged. Submit at least once per week — **before the week ends**. A day with no entries is always wrong.

**When to check:** Friday after 3 PM (local time) OR Monday before noon.  
**Frequency:** Maximum 1 reminder per week — track with `memory/heartbeat-state.json` key `clockify_last_prompt`.

**Steps:**
1. Read `memory/heartbeat-state.json` — if `clockify_last_prompt` was less than 5 days ago, skip.
2. Run: `cd /path/to/nimble-clockify && python3 clockify-auto.py status`
3. If there are pending days → send a message:
   > "Hey — you have [N] unlogged weekdays in Clockify ([start date] → [end date]). Per Nimble policy, every weekday must be covered before the week ends. What did you work on?"
4. Update `clockify_last_prompt` with the current timestamp.
5. When the user replies with what they worked on → activate the `clockify` skill (see `skills/clockify/SKILL.md`).

**If the user mentions PTO, sick days, bench (Idle), or UTO:** remind them those require HR authorization and must be logged in Clockify with the correct Activity (PTO/UTO/Idle) — the bulk script only handles regular workdays and Argentina holidays.
