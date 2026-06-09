#!/usr/bin/env python3
"""
Non-interactive Clockify helper for OpenClaw agent use.
Place this file in the same directory as main.py (shares the same .env).

Usage:
  python clockify-auto.py status
      Show pending days since last Clockify entry.

  python clockify-auto.py preview --desc "NexStar widget refactor" --verbose
      Dry run with client, project, activity (taskId), tag, and full API payload per day.

  python clockify-auto.py plan --desc "NexStar widget refactor" -o week-plan.json
      Export editable week plan JSON — tweak desc/activity/tag/project per day.

  python clockify-auto.py preview --plan-file week-plan.json --verbose
      Dry run from edited plan file.

  python clockify-auto.py create --plan-file week-plan.json
      Upload entries from edited plan file.

  python clockify-auto.py preview --entries '[{"from":"2026-04-14","to":"2026-04-16","desc":"Bug fixes","activity":"Working Time"}]'
      Dry run with per-range descriptions and optional activity/tag overrides.
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests

import clockify_lib as clib

# ── Load .env ──────────────────────────────────────────────────────────────────
_env_path = os.path.join(os.path.dirname(__file__) or ".", ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── Config ─────────────────────────────────────────────────────────────────────
API = "https://api.clockify.me/api/v1"
API_KEY = os.environ.get("CLOCKIFY_API_KEY", "PUT_YOUR_API_KEY_HERE")
WORKSPACE_NAME = os.environ.get("CLOCKIFY_WORKSPACE_NAME") or None
CLIENT_NAME = os.environ.get("CLOCKIFY_CLIENT_NAME") or None
PROJECT_NAME = os.environ.get("CLOCKIFY_PROJECT_NAME", "NexStar")
PTO_PROJECT_NAME = os.environ.get("CLOCKIFY_PTO_PROJECT_NAME") or None
ACTIVITY_NAME = os.environ.get("CLOCKIFY_ACTIVITY_NAME", "Working Time")
PTO_ACTIVITY_NAME = os.environ.get("CLOCKIFY_PTO_ACTIVITY_NAME", "PTO")
HOLIDAY_DESCRIPTION = os.environ.get("CLOCKIFY_HOLIDAY_DESCRIPTION", "Public holiday — Argentina")
TZ = os.environ.get("CLOCKIFY_TZ", "America/Bogota")
START_TIME = os.environ.get("CLOCKIFY_START_TIME", "08:00")
END_TIME = os.environ.get("CLOCKIFY_END_TIME", "16:00")
AR_HOLIDAYS_API = "https://api.argentinadatos.com/v1/feriados"
BILLABLE = True

# ── API helpers ────────────────────────────────────────────────────────────────
def hdrs():
    return {"X-Api-Key": API_KEY, "Content-Type": "application/json"}

def iso(dt_utc):
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

def daterange(d1, d2):
    d = d1
    while d <= d2:
        yield d
        d += timedelta(days=1)

def get_user():
    r = requests.get(f"{API}/user", headers=hdrs())
    r.raise_for_status()
    return r.json()

def get_workspaces():
    r = requests.get(f"{API}/workspaces", headers=hdrs())
    r.raise_for_status()
    return r.json()

def find_workspace_id():
    wss = get_workspaces()
    if not wss:
        sys.exit("No workspaces found.")
    if WORKSPACE_NAME:
        for ws in wss:
            if ws["name"] == WORKSPACE_NAME:
                return ws["id"]
        sys.exit(f'Workspace "{WORKSPACE_NAME}" not found.')
    return wss[0]["id"]

def list_projects(ws_id):
    r = requests.get(f"{API}/workspaces/{ws_id}/projects", headers=hdrs(), params={"page-size": 5000})
    r.raise_for_status()
    return r.json()

def find_project_id(ws_id, project_name=None, client_name=None):
    name = project_name if project_name is not None else PROJECT_NAME
    client = client_name if client_name is not None else CLIENT_NAME
    return clib.find_project_id(ws_id, hdrs, requests, list_projects, name, client)

def list_tags(ws_id):
    r = requests.get(f"{API}/workspaces/{ws_id}/tags", headers=hdrs(), params={"page-size": 5000})
    r.raise_for_status()
    return r.json()

def find_tag_id(ws_id, tag_name=None, required=True):
    return clib.find_tag_id(ws_id, tag_name, list_tags, required)

def find_task_id(ws_id, project_id, task_name, required=True):
    return clib.find_task_id(ws_id, project_id, task_name, hdrs, requests, required)

def get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id=None):
    params = {"start": iso(start_utc), "end": iso(end_utc), "page-size": 500}
    if project_id:
        params["project"] = project_id
    r = requests.get(f"{API}/workspaces/{ws_id}/user/{user_id}/time-entries", headers=hdrs(), params=params)
    r.raise_for_status()
    return r.json()

def entry_start_date(entry):
    s = entry.get("timeInterval", {}).get("start") or entry.get("start")
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()

def get_last_date_with_entries(ws_id, user_id, project_id=None):
    tz_utc = ZoneInfo("UTC")
    end_utc = datetime.now(tz_utc)
    start_utc = end_utc - timedelta(days=400)
    entries = get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id)
    dates = [entry_start_date(e) for e in entries if entry_start_date(e)]
    return max(dates) if dates else None

def get_dates_with_entries_in_range(ws_id, user_id, d1, d2, project_id=None):
    tz_utc = ZoneInfo("UTC")
    start_utc = datetime.combine(d1, time(0, 0), tzinfo=tz_utc)
    end_utc = datetime.combine(d2, time(23, 59, 59), tzinfo=tz_utc)
    entries = get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id)
    return {entry_start_date(e) for e in entries if entry_start_date(e)}

def friday_of_week(d):
    w = d.weekday()
    if w <= 4:
        return d + timedelta(days=4 - w)
    return d - timedelta(days=w - 4)

def monday_of_week(d):
    return d - timedelta(days=d.weekday())

def get_argentina_holidays_in_range(d1, d2):
    years = {d1.year, d2.year}
    out = {}
    for y in years:
        try:
            r = requests.get(f"{AR_HOLIDAYS_API}/{y}", timeout=10)
            r.raise_for_status()
            for item in r.json():
                d = datetime.strptime(item["fecha"], "%Y-%m-%d").date()
                if d1 <= d <= d2:
                    out[d] = item.get("nombre", "Public holiday")
        except Exception as e:
            print(f"Warning: could not load Argentina holidays for {y}: {e}", file=sys.stderr)
    return out

def holiday_description(day, holidays_map):
    name = holidays_map.get(day)
    if name:
        return f"Public holiday — {name}"
    return HOLIDAY_DESCRIPTION

def create_entry(ws_id, start_utc, end_utc, description, project_id, tag_ids=None, task_id=None):
    payload = clib.create_entry_payload(
        iso(start_utc), iso(end_utc), description, project_id, tag_ids, task_id, BILLABLE,
    )
    r = requests.post(f"{API}/workspaces/{ws_id}/time-entries", headers=hdrs(), json=payload)
    r.raise_for_status()
    return r.json()

def resolve_entry_plan(
    ws_id,
    desc,
    is_holiday,
    activity=None,
    tag=None,
    project_name=None,
    client_name=None,
):
    """Return resolved entry metadata for one day."""
    tag_name = clib.infer_tag(desc, is_holiday=is_holiday, explicit=tag)
    is_pto = is_holiday or clib.needs_pto_activity(tag_name)
    activity_name = clib.infer_activity(
        desc,
        is_holiday=is_holiday,
        is_pto=is_pto,
        explicit=activity,
        default=ACTIVITY_NAME,
        pto_name=PTO_ACTIVITY_NAME,
    )

    proj = project_name
    client = client_name
    if not proj:
        proj = PTO_PROJECT_NAME or PROJECT_NAME if is_pto else PROJECT_NAME
    if not client:
        client = CLIENT_NAME

    project_id = find_project_id(ws_id, proj, client)
    client_label, project_label = clib.project_client_names(
        ws_id, project_id, hdrs, requests, list_projects,
    )
    task_id = find_task_id(ws_id, project_id, activity_name, required=False)
    tag_ids = None
    tag_id_labels = []
    if tag_name:
        tid = find_tag_id(ws_id, tag_name, required=True)
        tag_ids = [tid]
        tag_id_labels = [tag_name]

    warnings = []
    if activity_name and not task_id:
        warnings.append(f'Activity "{activity_name}" not found on project "{project_label}" — taskId will be omitted.')

    return {
        "client": client_label,
        "project": project_label,
        "project_id": project_id,
        "activity": activity_name,
        "task_id": task_id,
        "tag": tag_name,
        "tag_ids": tag_ids,
        "tag_names": tag_id_labels,
        "warnings": warnings,
    }


def day_time_bounds(day):
    tz = ZoneInfo(TZ)
    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))
    start_local = datetime.combine(day, time(sh, sm), tzinfo=tz)
    end_local = datetime.combine(day, time(eh, em), tzinfo=tz)
    start_utc = start_local.astimezone(ZoneInfo("UTC"))
    end_utc = end_local.astimezone(ZoneInfo("UTC"))
    return start_utc, end_utc


def build_api_payload(ws_id, item):
    """Build the exact JSON body Clockify would receive for one day."""
    resolved = resolve_entry_plan(
        ws_id,
        item["desc"],
        item["is_holiday"],
        item.get("activity"),
        item.get("tag"),
        item.get("project"),
        item.get("client"),
    )
    start_utc, end_utc = day_time_bounds(item["day"])
    payload = clib.create_entry_payload(
        iso(start_utc),
        iso(end_utc),
        item["desc"],
        resolved["project_id"],
        resolved["tag_ids"],
        resolved["task_id"],
        BILLABLE,
    )
    resolved["payload"] = payload
    resolved["start_local"] = f"{item['day']} {START_TIME}"
    resolved["end_local"] = f"{item['day']} {END_TIME}"
    return resolved


def day_item_to_plan_row(item, resolved):
    return {
        "date": str(item["day"]),
        "weekday": DAY_NAMES[item["day"].weekday()],
        "desc": item["desc"],
        "activity": resolved["activity"],
        "tag": resolved["tag"],
        "project": resolved["project"],
        "client": resolved["client"],
        "is_holiday": item["is_holiday"],
    }


def plan_rows_to_day_items(plan_rows):
    days = []
    for row in plan_rows:
        days.append({
            "day": datetime.strptime(row["date"], "%Y-%m-%d").date(),
            "desc": row["desc"],
            "is_holiday": row.get("is_holiday", False),
            "activity": row.get("activity"),
            "tag": row.get("tag"),
            "project": row.get("project"),
            "client": row.get("client"),
        })
    return days


def load_entries_arg(entries_json=None, plan_file=None):
    if plan_file:
        with open(plan_file) as f:
            data = json.load(f)
        if "days" not in data:
            sys.exit("Plan file must contain a 'days' array.")
        return None, plan_rows_to_day_items(data["days"])
    if entries_json:
        try:
            return json.loads(entries_json), None
        except json.JSONDecodeError as e:
            sys.exit(f"Error parsing --entries JSON: {e}")
    return None, None

# ── Core logic ─────────────────────────────────────────────────────────────────

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def compute_pending_range():
    """Return (start_date, end_date, last_entry_date) for the pending range."""
    today = date.today()
    user = get_user()
    ws_id = find_workspace_id()
    project_id = find_project_id(ws_id)
    last_date = get_last_date_with_entries(ws_id, user["id"], project_id=None)
    start_date = last_date + timedelta(days=1) if last_date else monday_of_week(today)
    end_date = friday_of_week(today)
    return start_date, end_date, last_date, ws_id, user["id"], project_id

def build_day_list(start_date, end_date, ws_id, user_id, project_id, entries):
    """
    Build list of days to create.
    `entries` items: {from, to, desc, activity?, tag?}
    Returns list of dicts with day, desc, is_holiday, activity, tag.
    """
    existing = get_dates_with_entries_in_range(ws_id, user_id, start_date, end_date, project_id=None)
    holidays_map = get_argentina_holidays_in_range(start_date, end_date)

    meta_map = {}
    for entry in entries:
        d1 = datetime.strptime(entry["from"], "%Y-%m-%d").date()
        d2 = datetime.strptime(entry["to"], "%Y-%m-%d").date()
        for d in daterange(d1, d2):
            meta_map[d] = {
                "desc": entry.get("desc", "Work"),
                "activity": entry.get("activity"),
                "tag": entry.get("tag"),
            }

    days = []
    for day in daterange(start_date, end_date):
        if day.weekday() >= 5:
            continue
        if day in existing:
            continue
        is_holiday = day in holidays_map
        meta = meta_map.get(day, {})
        desc = holiday_description(day, holidays_map) if is_holiday else meta.get("desc")
        days.append({
            "day": day,
            "desc": desc,
            "is_holiday": is_holiday,
            "activity": meta.get("activity"),
            "tag": meta.get("tag"),
        })

    return days

def hours_per_day():
    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))
    return (eh - sh) + (em - sm) / 60


# ── Commands ───────────────────────────────────────────────────────────────────

def cmd_status():
    """Show pending days — no description needed."""
    start_date, end_date, last_date, ws_id, user_id, project_id = compute_pending_range()

    if start_date > end_date:
        print("Clockify is up to date. No pending days.")
        return

    existing = get_dates_with_entries_in_range(ws_id, user_id, start_date, end_date, project_id=None)
    holidays_map = get_argentina_holidays_in_range(start_date, end_date)

    pending = []
    for day in daterange(start_date, end_date):
        if day.weekday() >= 5:
            continue
        if day in existing:
            continue
        pending.append(day)

    if not pending:
        print("Clockify is up to date. No pending days.")
        return

    hpd = hours_per_day()
    total_h = len(pending) * hpd

    print(f"Last entry: {last_date or 'none'}")
    print(f"Pending range: {start_date} → {end_date}")
    print(f"Pending workdays: {len(pending)}")
    print(f"Total hours to log: {total_h:.2f}h ({hpd:.1f}h/day, {START_TIME}–{END_TIME})")
    print()
    print("Pending days:")
    for day in pending:
        tag = " [AR holiday — PTO + Holiday]" if day in holidays_map else ""
        print(f"  {DAY_NAMES[day.weekday()]} {day}{tag}")


def print_day_preview(item, resolved, verbose=False):
    day = item["day"]
    tag_label = resolved["tag"] or "(none)"
    print(f"  {DAY_NAMES[day.weekday()]} {day}")
    print(f"    client:      {resolved['client']}")
    print(f"    project:     {resolved['project']} (id: {resolved['project_id']})")
    print(f"    activity:    {resolved['activity']} (taskId: {resolved['task_id'] or 'MISSING'})")
    print(f"    tag:         {tag_label}")
    print(f"    description: {item['desc']}")
    print(f"    time:        {resolved['start_local']} → {resolved['end_local']} ({TZ})")
    for w in resolved["warnings"]:
        print(f"    ⚠️  {w}")
    if verbose:
        print("    API payload:")
        print(json.dumps(resolved["payload"], indent=6))


def cmd_plan(desc=None, entries_json=None, plan_file=None, output=None):
    """Export an editable week plan JSON (modify days, then create --plan-file)."""
    start_date, end_date, last_date, ws_id, user_id, project_id = compute_pending_range()
    if start_date > end_date:
        print("No pending days. Clockify is up to date.")
        return

    entries, plan_days = load_entries_arg(entries_json, plan_file)
    if plan_days:
        days = plan_days
    elif desc:
        entries = [{"from": str(start_date), "to": str(end_date), "desc": desc}]
        days = build_day_list(start_date, end_date, ws_id, user_id, project_id, entries)
    elif entries:
        days = build_day_list(start_date, end_date, ws_id, user_id, project_id, entries)
    else:
        sys.exit("Use --desc, --entries, or --plan-file to build a plan.")

    if not days:
        print("All days in the range already have entries. Nothing to plan.")
        return

    plan = {
        "generated_at": datetime.now().isoformat(),
        "pending_range": {"from": str(start_date), "to": str(end_date)},
        "schedule": {"start": START_TIME, "end": END_TIME, "tz": TZ},
        "instructions": (
            "Edit any day below (desc, activity, tag, project, client), then run: "
            "python clockify-auto.py preview --plan-file <this-file> --verbose "
            "and python clockify-auto.py create --plan-file <this-file>"
        ),
        "days": [],
    }

    for item in days:
        resolved = build_api_payload(ws_id, item)
        plan["days"].append(day_item_to_plan_row(item, resolved))

    text = json.dumps(plan, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w") as f:
            f.write(text)
        print(f"Week plan written to {output} ({len(plan['days'])} days).")
        print("Edit the file, then: preview --plan-file ... --verbose")
    else:
        print(text)


def cmd_preview_or_create(mode, desc=None, entries_json=None, plan_file=None, verbose=False):
    """mode='preview' or mode='create'"""
    start_date, end_date, last_date, ws_id, user_id, project_id = compute_pending_range()

    if start_date > end_date:
        print("No pending days. Clockify is up to date.")
        return

    entries, plan_days = load_entries_arg(entries_json, plan_file)
    if plan_days:
        days = plan_days
    elif entries_json or desc:
        if not entries:
            entries = [{"from": str(start_date), "to": str(end_date), "desc": desc}]
        days = build_day_list(start_date, end_date, ws_id, user_id, project_id, entries)
    else:
        sys.exit("You must pass --desc, --entries, or --plan-file")

    if not days:
        print("All days in the range already have entries. Nothing to create.")
        return

    missing_desc = [item for item in days if not item["desc"] and not item["is_holiday"]]
    if missing_desc:
        print("ERROR: Missing descriptions for these days:")
        for item in missing_desc:
            print(f"  {DAY_NAMES[item['day'].weekday()]} {item['day']}")
        print()
        print("Use --entries or --plan-file with ranges that cover all pending workdays.")
        sys.exit(1)

    hpd = hours_per_day()
    total_h = len(days) * hpd
    work_days = [item for item in days if not item["is_holiday"]]
    holiday_days = [item for item in days if item["is_holiday"]]

    print(f"{'DRY RUN / PREVIEW' if mode == 'preview' else 'CREATING ENTRIES'}")
    print(f"{'─' * 40}")
    print(f"Last entry:       {last_date or 'none'}")
    print(f"Range:            {start_date} → {end_date}")
    print(f"Days to create:   {len(days)} ({len(work_days)} work + {len(holiday_days)} AR holidays)")
    print(f"Schedule:         {START_TIME}–{END_TIME} ({hpd:.1f}h/day)")
    print(f"Total hours:      {total_h:.2f}h")
    print()
    print("Day-by-day (exact Clockify mapping):")

    resolved_days = []
    for item in days:
        resolved = build_api_payload(ws_id, item)
        resolved_days.append((item, resolved))
        print_day_preview(item, resolved, verbose=verbose)
        print()

    if mode == "preview":
        print("(Dry run only — run 'create' with the same args to upload)")
        if plan_file:
            print(f"To tweak the week, edit {plan_file} and preview again.")
        else:
            print("Tip: export an editable plan with: python clockify-auto.py plan --desc '...' --output week-plan.json")
        return

    print()
    created = 0
    for item, resolved in resolved_days:
        start_utc, end_utc = day_time_bounds(item["day"])
        create_entry(
            ws_id,
            start_utc,
            end_utc,
            item["desc"],
            resolved["project_id"],
            resolved["tag_ids"],
            resolved["task_id"],
        )
        tag_label = f" + {resolved['tag']}" if resolved["tag"] else ""
        print(f"  [ok] {item['day']} → {resolved['activity']}{tag_label} | {item['desc']}")
        created += 1

    print()
    print(f"Done. Entries created: {created} | Total hours: {total_h:.2f}h")


def cmd_discover():
    """List Client → Project → Activity hierarchy and available Nimble tags."""
    ws_id = find_workspace_id()
    clients = clib.client_name_map(ws_id, hdrs, requests)
    projects = list_projects(ws_id)
    tags = list_tags(ws_id)

    print("CLIENT → PROJECT → ACTIVITY")
    print("=" * 50)
    by_client = {}
    for p in projects:
        cname = clients.get(p.get("clientId"), "(no client)")
        by_client.setdefault(cname, []).append(p)

    for cname in sorted(by_client):
        print(f"\nCLIENT: {cname}")
        for p in sorted(by_client[cname], key=lambda x: x["name"]):
            print(f"  PROJECT: {p['name']} (id: {p['id']})")
            try:
                tasks = clib.list_tasks(ws_id, p["id"], hdrs, requests)
                for t in sorted(tasks, key=lambda x: x["name"]):
                    print(f"    ACTIVITY: {t['name']} (id: {t['id']})")
            except Exception as e:
                print(f"    (could not load activities: {e})")

    print("\nTAGS (Nimble June 2026)")
    print("=" * 50)
    tag_names = {t["name"] for t in tags}
    for key, name in clib.NIMBLE_TAGS.items():
        mark = "✅" if name in tag_names else "❌ missing"
        print(f"  {mark}  {name}")
    print()
    print("Configured in .env:")
    print(f"  CLOCKIFY_CLIENT_NAME={CLIENT_NAME or '(not set)'}")
    print(f"  CLOCKIFY_PROJECT_NAME={PROJECT_NAME}")
    print(f"  CLOCKIFY_ACTIVITY_NAME={ACTIVITY_NAME}")
    print(f"  CLOCKIFY_PTO_ACTIVITY_NAME={PTO_ACTIVITY_NAME}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Clockify non-interactive helper for OpenClaw agent.")
    ap.add_argument(
        "command",
        choices=["status", "discover", "plan", "preview", "create"],
        help="Command to run",
    )
    ap.add_argument("--desc", help="Single description for all pending workdays")
    ap.add_argument(
        "--entries",
        help='JSON array: [{"from":"YYYY-MM-DD","to":"YYYY-MM-DD","desc":"...","activity":"Working Time","tag":null}]',
    )
    ap.add_argument(
        "--plan-file",
        help="Editable week plan JSON (from plan command). Use to preview/create after editing.",
    )
    ap.add_argument("--output", "-o", help="Output path for plan command (default: stdout)")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Show full Clockify API payload per day (dry run detail)",
    )
    args = ap.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command == "discover":
        cmd_discover()
    elif args.command == "plan":
        cmd_plan(desc=args.desc, entries_json=args.entries, plan_file=args.plan_file, output=args.output)
    elif args.command in ("preview", "create"):
        cmd_preview_or_create(
            args.command,
            desc=args.desc,
            entries_json=args.entries,
            plan_file=args.plan_file,
            verbose=args.verbose,
        )


if __name__ == "__main__":
    main()
