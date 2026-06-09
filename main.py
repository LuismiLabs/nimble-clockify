#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests

import clockify_lib as clib

# Load .env if present (for CLOCKIFY_API_KEY without exporting manually)
_env_path = os.path.join(os.path.dirname(__file__) or ".", ".env")
if os.path.isfile(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# python -m venv .venv && source .venv/bin/activate
# python main.py --from 2025-08-01 --to 2025-08-31 --desc "Login Radius tickets"
API = "https://api.clockify.me/api/v1"

# API Key: CLOCKIFY_API_KEY env var or .env file (do not commit the real key)
API_KEY = os.environ.get("CLOCKIFY_API_KEY", "PUT_YOUR_API_KEY_HERE")

# Fixed configuration (can be overridden via env/.env)
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
BILLABLE = True

# Argentina holidays API (no API key required)
AR_HOLIDAYS_API = "https://api.argentinadatos.com/v1/feriados"

def hdrs():
    return {"X-Api-Key": API_KEY, "Content-Type": "application/json"}

def iso(dt_utc):
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

def ymd(s):
    return datetime.strptime(s, "%Y-%m-%d").date()

def daterange(d1: date, d2: date):
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
        raise SystemExit("No workspaces found in your account.")
    if WORKSPACE_NAME:
        for ws in wss:
            if ws["name"] == WORKSPACE_NAME:
                return ws["id"]
        raise SystemExit(f'Workspace "{WORKSPACE_NAME}" not found.')
    return wss[0]["id"]

def list_projects(ws_id):
    r = requests.get(f"{API}/workspaces/{ws_id}/projects",
                     headers=hdrs(), params={"page-size":5000})
    r.raise_for_status()
    return r.json()

def find_project_id(ws_id, project_name=None, client_name=None):
    name = project_name if project_name is not None else PROJECT_NAME
    client = client_name if client_name is not None else CLIENT_NAME
    return clib.find_project_id(ws_id, hdrs, requests, list_projects, name, client)

def list_tasks(ws_id, project_id):
    return clib.list_tasks(ws_id, project_id, hdrs, requests)

def find_task_id(ws_id, project_id, task_name, required=True):
    return clib.find_task_id(ws_id, project_id, task_name, hdrs, requests, required)

def list_tags(ws_id):
    r = requests.get(f"{API}/workspaces/{ws_id}/tags",
                     headers=hdrs(), params={"page-size":5000})
    r.raise_for_status()
    return r.json()

def find_tag_id(ws_id, tag_name=None, required=True):
    return clib.find_tag_id(ws_id, tag_name, list_tags, required)

def create_entry(ws_id, start_utc, end_utc, description, project_id, tag_ids=None, task_id=None):
    payload = clib.create_entry_payload(
        iso(start_utc), iso(end_utc), description, project_id, tag_ids, task_id, BILLABLE,
    )
    r = requests.post(f"{API}/workspaces/{ws_id}/time-entries",
                      headers=hdrs(), json=payload)
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
    if tag_name:
        tag_ids = [find_tag_id(ws_id, tag_name, required=True)]

    warnings = []
    if activity_name and not task_id:
        warnings.append(
            f'Activity "{activity_name}" not found on project "{project_label}" — taskId will be omitted.',
        )

    return {
        "client": client_label,
        "project": project_label,
        "project_id": project_id,
        "activity": activity_name,
        "task_id": task_id,
        "tag": tag_name,
        "tag_ids": tag_ids,
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


def build_api_payload(ws_id, day, desc, is_holiday, activity=None, tag=None, project=None, client=None):
    """Build the exact JSON body Clockify would receive for one day."""
    resolved = resolve_entry_plan(
        ws_id, desc, is_holiday, activity, tag, project, client,
    )
    start_utc, end_utc = day_time_bounds(day)
    payload = clib.create_entry_payload(
        iso(start_utc),
        iso(end_utc),
        desc,
        resolved["project_id"],
        resolved["tag_ids"],
        resolved["task_id"],
        BILLABLE,
    )
    resolved["payload"] = payload
    resolved["start_local"] = f"{day} {START_TIME}"
    resolved["end_local"] = f"{day} {END_TIME}"
    return resolved


def print_day_preview(day, desc, resolved, verbose=False):
    tag_label = resolved["tag"] or "(none)"
    print(f"  {day}")
    print(f"    client:      {resolved['client']}")
    print(f"    project:     {resolved['project']} (id: {resolved['project_id']})")
    print(f"    activity:    {resolved['activity']} (taskId: {resolved['task_id'] or 'MISSING'})")
    print(f"    tag:         {tag_label}")
    print(f"    description: {desc}")
    print(f"    time:        {resolved['start_local']} → {resolved['end_local']} ({TZ})")
    for w in resolved["warnings"]:
        print(f"    ⚠️  {w}")
    if verbose:
        print("    API payload:")
        print(json.dumps(resolved["payload"], indent=6))


def export_week_plan(ws_id, d1, d2, desc, holidays_map, output=None, include_weekends=False):
    """Export an editable JSON plan for the date range."""
    plan = {
        "generated_at": datetime.now().isoformat(),
        "range": {"from": str(d1), "to": str(d2)},
        "schedule": {"start": START_TIME, "end": END_TIME, "tz": TZ},
        "instructions": (
            "Edit any day below (desc, activity, tag, project, client), then run: "
            "python main.py --from ... --to ... --plan-file <this-file> --dry-run --verbose"
        ),
        "days": [],
    }

    for day in daterange(d1, d2):
        if not include_weekends and day.weekday() >= 5:
            continue
        is_holiday = day in holidays_map
        day_desc = holiday_description(day, holidays_map) if is_holiday else desc
        resolved = build_api_payload(ws_id, day, day_desc, is_holiday)
        plan["days"].append({
            "date": str(day),
            "weekday": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][day.weekday()],
            "desc": day_desc,
            "activity": resolved["activity"],
            "tag": resolved["tag"],
            "project": resolved["project"],
            "client": resolved["client"],
            "is_holiday": is_holiday,
        })

    text = json.dumps(plan, indent=2, ensure_ascii=False)
    if output:
        with open(output, "w") as f:
            f.write(text)
        print(f"Week plan written to {output} ({len(plan['days'])} days).")
    else:
        print(text)


def load_plan_days(plan_file):
    with open(plan_file) as f:
        data = json.load(f)
    if "days" not in data:
        raise SystemExit("Plan file must contain a 'days' array.")
    return data["days"]

def get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id=None):
    """Fetch user time entries in the workspace for the range [start_utc, end_utc]."""
    params = {
        "start": iso(start_utc),
        "end": iso(end_utc),
        "page-size": 500,
    }
    if project_id:
        params["project"] = project_id
    r = requests.get(
        f"{API}/workspaces/{ws_id}/user/{user_id}/time-entries",
        headers=hdrs(),
        params=params,
    )
    r.raise_for_status()
    return r.json()

def _entry_start_date(entry):
    """Extract the date from a time entry's start."""
    s = entry.get("timeInterval", {}).get("start") or entry.get("start")
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()

def get_last_date_with_entries(ws_id, user_id, project_id=None):
    """
    Return the latest date on which the user has at least one entry in this project/workspace.
    Returns None if there are no entries.
    """
    tz_utc = ZoneInfo("UTC")
    end_utc = datetime.now(tz_utc)
    start_utc = end_utc - timedelta(days=400)
    entries = get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id)
    dates = [_entry_start_date(e) for e in entries if _entry_start_date(e)]
    return max(dates) if dates else None

def get_dates_with_entries_in_range(ws_id, user_id, d1, d2, project_id=None):
    """Return a set of dates that already have at least one entry in [d1, d2]."""
    tz_utc = ZoneInfo("UTC")
    start_utc = datetime.combine(d1, time(0, 0), tzinfo=tz_utc)
    end_utc = datetime.combine(d2, time(23, 59, 59), tzinfo=tz_utc)
    entries = get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id)
    return {_entry_start_date(e) for e in entries if _entry_start_date(e)}

def friday_of_week(d: date):
    """Friday of the week containing d. If d is Sat/Sun, returns the previous Friday."""
    w = d.weekday()
    if w <= 4:
        return d + timedelta(days=4 - w)
    return d - timedelta(days=w - 4)

def monday_of_week(d: date):
    """Monday of the week containing d."""
    return d - timedelta(days=d.weekday())

def get_argentina_holidays(year: int):
    """Fetch Argentina public holidays for a year (ArgentinaDatos API, no API key)."""
    r = requests.get(f"{AR_HOLIDAYS_API}/{year}", timeout=10)
    r.raise_for_status()
    return r.json()

def get_argentina_holidays_in_range(d1: date, d2: date):
    """Return a dict of date -> holiday name for Argentina public holidays in [d1, d2]."""
    years = {d1.year, d2.year}
    out = {}
    for y in years:
        try:
            for item in get_argentina_holidays(y):
                d = datetime.strptime(item["fecha"], "%Y-%m-%d").date()
                if d1 <= d <= d2:
                    out[d] = item.get("nombre", "Public holiday")
        except requests.RequestException as e:
            raise SystemExit(f"Failed to load Argentina holidays ({y}): {e}")
    return out

def holiday_description(day: date, holidays_map):
    """Build description for a public holiday entry (Activity: PTO, Tag: Holiday)."""
    name = holidays_map.get(day)
    if name:
        return f"Public holiday — {name}"
    return HOLIDAY_DESCRIPTION

def list_workspaces_and_projects():
    """List all workspaces and projects with their IDs."""
    print("🔍 AVAILABLE WORKSPACES:")
    print("=" * 50)

    workspaces = get_workspaces()
    for i, ws in enumerate(workspaces, 1):
        print(f"{i}. {ws['name']} (ID: {ws['id']})")

        try:
            projects = list_projects(ws['id'])
            if projects:
                print("   📁 Projects:")
                for j, proj in enumerate(projects, 1):
                    print(f"      {j}. {proj['name']} (ID: {proj['id']})")
            else:
                print("   📁 No projects")
        except Exception as e:
            print(f"   ❌ Error fetching projects: {e}")
        print()

    print("🏷️  AVAILABLE TAGS:")
    print("=" * 50)
    if workspaces:
        try:
            tags = list_tags(workspaces[0]['id'])
            for i, tag in enumerate(tags, 1):
                print(f"{i}. {tag['name']} (ID: {tag['id']})")
        except Exception as e:
            print(f"❌ Error fetching tags: {e}")

    print("\n💡 Copy the correct names/IDs and update the variables in the code:")
    print(f"   WORKSPACE_NAME = 'workspace_name'  # or None to use the first one")
    print(f"   PROJECT_NAME = 'project_name'")
    print(f"   CLOCKIFY_CLIENT_NAME = 'Nexstar Media Inc'")
    print(f"   CLOCKIFY_ACTIVITY_NAME = 'Working Time'")

def discover_structure():
    """List Client → Project → Activity hierarchy and Nimble tags."""
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
            print(f"  PROJECT: {p['name']} (ID: {p['id']})")
            try:
                for t in sorted(list_tasks(ws_id, p["id"]), key=lambda x: x["name"]):
                    print(f"    ACTIVITY: {t['name']} (ID: {t['id']})")
            except Exception as e:
                print(f"    (could not load activities: {e})")

    print("\nTAGS (Nimble June 2026)")
    print("=" * 50)
    tag_names = {t["name"] for t in tags}
    for _, name in clib.NIMBLE_TAGS.items():
        mark = "✅" if name in tag_names else "❌ missing"
        print(f"  {mark}  {name}")

def list_tags_and_validate_holiday():
    """List all tags and validate Nimble June 2026 tags exist."""
    ws_id = find_workspace_id()
    print("🏷️  TAGS IN YOUR WORKSPACE:")
    print("=" * 50)
    tags = list_tags(ws_id)
    nimble_names = set(clib.NIMBLE_TAGS.values())
    for i, t in enumerate(tags, 1):
        mark = " ← Nimble" if t["name"] in nimble_names else ""
        print(f"   {i}. {t['name']} (ID: {t['id']}){mark}")
    print()
    tag_names = {t["name"] for t in tags}
    for _, name in clib.NIMBLE_TAGS.items():
        if name in tag_names:
            print(f"   ✅ '{name}' found.")
        else:
            print(f"   ❌ '{name}' missing — create it in Clockify.")
    print()

def run_weekly_interactive():
    """
    Weekly mode: ask for description, compute range from the day after the last
    day with entries to this week's Friday, and create entries only for days that
    don't have any yet (Mon–Fri; Argentina holidays get Holiday tag).
    """
    today = date.today()
    user = get_user()
    user_id = user["id"]
    ws_id = find_workspace_id()
    tz = ZoneInfo(TZ)
    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))

    print("📅 Weekly mode: upload hours from the last day with entries to this week's Friday.")
    print("   (Mon–Fri only; days that already have entries are skipped; Argentina holidays → Holiday.)")
    print()
    desc = input("What did you work on? ").strip() or "Work"
    print()

    last_date = get_last_date_with_entries(ws_id, user_id, project_id=None)
    start_date = last_date + timedelta(days=1) if last_date else monday_of_week(today)
    end_date = friday_of_week(today)

    if start_date > end_date:
        print("No workdays left in this range.")
        return

    existing_dates = get_dates_with_entries_in_range(ws_id, user_id, start_date, end_date, project_id=None)
    holidays_map = get_argentina_holidays_in_range(start_date, end_date)

    to_create = []
    for day in daterange(start_date, end_date):
        if day.weekday() >= 5:
            continue
        if day in existing_dates:
            continue
        to_create.append(day)

    if not to_create:
        print("All workdays in the range already have entries. Nothing to create.")
        return

    workdays_count = len([d for d in to_create if d not in holidays_map])
    holidays_count = len([d for d in to_create if d in holidays_map])
    hours_per_day = (eh - sh) + (em - sm) / 60
    total_hours = len(to_create) * hours_per_day

    print(f"📅 SUMMARY:")
    print(f"   Last day with entries: {last_date or 'none'}")
    print(f"   Range to create: {start_date} → {end_date}")
    print(f"   Days to create: {len(to_create)} ({workdays_count} work + {holidays_count} Argentina holidays)")
    print(f"   Description (work): {desc}")
    print(f"   Total hours: {total_hours:.2f}h")
    print()

    confirm = input("Create these entries? [y/N]: ").strip().lower()
    if confirm not in ("s", "si", "sí", "y", "yes"):
        print("Cancelled.")
        return

    created = 0
    for day in to_create:
        start_local = datetime.combine(day, time(sh, sm), tzinfo=tz)
        end_local = datetime.combine(day, time(eh, em), tzinfo=tz)
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_local.astimezone(ZoneInfo("UTC"))
        is_holiday = day in holidays_map
        day_desc = holiday_description(day, holidays_map) if is_holiday else desc
        resolved = resolve_entry_plan(ws_id, day_desc, is_holiday)
        te = create_entry(
            ws_id, start_utc, end_utc, day_desc,
            resolved["project_id"], resolved["tag_ids"], resolved["task_id"],
        )
        tag_label = f" + {resolved['tag']}" if resolved["tag"] else ""
        print(f"[ok] {day} created ({resolved['activity']}{tag_label} | {day_desc})")
        created += 1

    print(f"\nDone. Entries created: {created} | Total hours: {total_hours:.2f}h")

def calculate_hours(d1: date, d2: date, include_weekends=False):
    """Compute total work hours in the date range."""
    total_hours = 0
    workdays = 0

    for day in daterange(d1, d2):
        if not include_weekends and day.weekday() >= 5:  # skip Sat/Sun
            continue
        workdays += 1

    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))
    hours_per_day = (eh - sh) + (em - sm) / 60

    total_hours = workdays * hours_per_day

    return workdays, total_hours, hours_per_day

def main():
    ap = argparse.ArgumentParser(description="Log Mon–Fri hours to Clockify with Argentina holidays support.")
    ap.add_argument("--list", action="store_true", help="List workspaces, projects, and tags")
    ap.add_argument("--discover", action="store_true", help="List Client → Project → Activity hierarchy and Nimble tags")
    ap.add_argument("--list-tags", action="store_true", help="List tags and validate Nimble June 2026 tags")
    ap.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    ap.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    ap.add_argument("--desc", help="Description for time entries")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be created without creating entries")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="With --dry-run: show client, project, activity, tag, and full API payload per day",
    )
    ap.add_argument("--plan", action="store_true", help="Export editable week plan JSON (requires --from, --to, --desc)")
    ap.add_argument("--plan-file", help="Create entries from an edited plan JSON file")
    ap.add_argument("--output", "-o", help="Output path for --plan (default: stdout)")
    ap.add_argument("--include-weekends", action="store_true", help="Include Saturdays and Sundays")
    args = ap.parse_args()

    if args.list:
        list_workspaces_and_projects()
        return

    if args.discover:
        discover_structure()
        return

    if args.list_tags:
        list_tags_and_validate_holiday()
        return

    # Interactive weekly mode: no --from/--to/--desc → ask description, use last entry date to this week's Friday
    if not args.from_date and not args.to_date and not args.desc:
        run_weekly_interactive()
        return

    if args.plan:
        if not all([args.from_date, args.to_date, args.desc]):
            ap.error("--plan requires --from, --to, and --desc.")
        ws_id = find_workspace_id()
        d1, d2 = ymd(args.from_date), ymd(args.to_date)
        holidays_map = get_argentina_holidays_in_range(d1, d2)
        export_week_plan(ws_id, d1, d2, args.desc, holidays_map, args.output, args.include_weekends)
        return

    if args.plan_file:
        if not all([args.from_date, args.to_date]):
            ap.error("--plan-file requires --from and --to (same range used when the plan was generated).")
        ws_id = find_workspace_id()
        d1, d2 = ymd(args.from_date), ymd(args.to_date)
        plan_days = {row["date"]: row for row in load_plan_days(args.plan_file)}
    else:
        if not all([args.from_date, args.to_date, args.desc]):
            ap.error("--from, --to, and --desc are required to create time entries (or run with no args for weekly mode).")
        plan_days = None

    ws_id = find_workspace_id()
    tz = ZoneInfo(TZ)

    d1, d2 = ymd(args.from_date), ymd(args.to_date)
    holidays_map = get_argentina_holidays_in_range(d1, d2)

    # Compute and show total hours
    workdays, total_hours, hours_per_day = calculate_hours(d1, d2, args.include_weekends)
    holidays_in_scope = sum(1 for d in holidays_map if args.include_weekends or d.weekday() < 5)
    print(f"📅 SUMMARY:")
    print(f"   Range: {d1} → {d2}")
    print(f"   Days to create: {workdays} ({workdays - holidays_in_scope} work + {holidays_in_scope} Argentina holidays)")
    print(f"   Hours per day: {hours_per_day:.2f}h")
    print(f"   Total hours: {total_hours:.2f}h")
    print(f"   Schedule: {START_TIME} - {END_TIME}")
    print(f"   Include weekends: {'Yes' if args.include_weekends else 'No'}")
    if args.plan_file:
        print(f"   Plan file: {args.plan_file}")
    print()

    if args.dry_run and args.verbose:
        print("Day-by-day (exact Clockify mapping):")
        print()

    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))

    created = 0
    for day in daterange(d1, d2):
        if not args.include_weekends and day.weekday() >= 5:  # skip Sat/Sun
            continue

        start_local = datetime.combine(day, time(sh, sm), tzinfo=tz)
        end_local   = datetime.combine(day, time(eh, em), tzinfo=tz)
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc   = end_local.astimezone(ZoneInfo("UTC"))

        is_holiday = day in holidays_map
        if plan_days:
            row = plan_days.get(str(day))
            if not row:
                continue
            desc = row["desc"]
            is_holiday = row.get("is_holiday", is_holiday)
            resolved = build_api_payload(
                ws_id, day, desc, is_holiday,
                row.get("activity"), row.get("tag"), row.get("project"), row.get("client"),
            )
        else:
            desc = holiday_description(day, holidays_map) if is_holiday else args.desc
            resolved = build_api_payload(ws_id, day, desc, is_holiday)

        if args.dry_run:
            if args.verbose:
                print_day_preview(day, desc, resolved, verbose=True)
                print()
            else:
                tag_label = f" + {resolved['tag']}" if resolved["tag"] else ""
                print(
                    f"[DRY-RUN] {day} | {START_TIME}-{END_TIME} | "
                    f"{resolved['activity']}{tag_label} | {resolved['project']} | {desc}",
                )
        else:
            te = create_entry(
                ws_id, start_utc, end_utc, desc,
                resolved["project_id"], resolved["tag_ids"], resolved["task_id"],
            )
            print(f"[ok] {day} created id={te.get('id')} ({resolved['activity']} | {desc})")
        created += 1

    mode = "DRY-RUN (simulated)" if args.dry_run else "real"
    print(f"\nDone. Entries {mode}: {created} | Total hours: {total_hours:.2f}h")
    if args.dry_run and not args.verbose:
        print("Tip: add --verbose to see the full Clockify API payload per day.")
    if args.dry_run and not args.plan_file:
        print("Tip: export an editable plan with: python main.py --plan --from ... --to ... --desc '...' -o week-plan.json")

if __name__ == "__main__":
    main()
