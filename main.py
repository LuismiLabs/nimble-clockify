#!/usr/bin/env python3
import argparse
import os
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests

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
PROJECT_NAME = os.environ.get("CLOCKIFY_PROJECT_NAME", "NexStar")
TAG_NAME = os.environ.get("CLOCKIFY_TAG_NAME", "PHP")
HOLIDAY_TAG_NAME = os.environ.get("CLOCKIFY_HOLIDAY_TAG_NAME", "Vacation/Holiday")  # tag for holiday days (Argentina)
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

def find_project_id(ws_id):
    for p in list_projects(ws_id):
        if p["name"] == PROJECT_NAME:
            return p["id"]
    raise SystemExit(f'Project "{PROJECT_NAME}" not found in the workspace.')

def list_tags(ws_id):
    r = requests.get(f"{API}/workspaces/{ws_id}/tags",
                     headers=hdrs(), params={"page-size":5000})
    r.raise_for_status()
    return r.json()

def find_tag_id(ws_id, tag_name=None):
    name = tag_name if tag_name is not None else TAG_NAME
    for t in list_tags(ws_id):
        if t["name"] == name:
            return t["id"]
    raise SystemExit(f'Tag "{name}" not found in the workspace.')

def create_entry(ws_id, start_utc, end_utc, description, project_id, tag_id):
    payload = {
        "start": iso(start_utc),
        "end": iso(end_utc),
        "billable": BILLABLE,
        "description": description,
        "projectId": project_id,
        "tagIds": [tag_id],
    }
    r = requests.post(f"{API}/workspaces/{ws_id}/time-entries",
                      headers=hdrs(), json=payload)
    r.raise_for_status()
    return r.json()

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
    data = r.json()
    return [datetime.strptime(item["fecha"], "%Y-%m-%d").date() for item in data]

def get_argentina_holidays_in_range(d1: date, d2: date):
    """Return a set of dates that are Argentina public holidays in [d1, d2]."""
    years = {d1.year, d2.year}
    out = set()
    for y in years:
        try:
            for d in get_argentina_holidays(y):
                if d1 <= d <= d2:
                    out.add(d)
        except requests.RequestException as e:
            raise SystemExit(f"Failed to load Argentina holidays ({y}): {e}")
    return out

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
    print(f"   TAG_NAME = 'tag_name'")
    print(f"   HOLIDAY_TAG_NAME = 'holiday_tag_name'  # e.g. Vacation/Holiday")

def list_tags_and_validate_holiday():
    """List all tags in the workspace and validate that the holiday tag exists."""
    ws_id = find_workspace_id()
    print("🏷️  TAGS IN YOUR WORKSPACE:")
    print("=" * 50)
    tags = list_tags(ws_id)
    for i, t in enumerate(tags, 1):
        mark = " ← holidays" if t["name"] == HOLIDAY_TAG_NAME else ""
        print(f"   {i}. {t['name']} (ID: {t['id']}){mark}")
    print()
    found = any(t["name"] == HOLIDAY_TAG_NAME for t in tags)
    if found:
        print(f"   ✅ Holiday tag '{HOLIDAY_TAG_NAME}' found.")
    else:
        print(f"   ❌ Holiday tag '{HOLIDAY_TAG_NAME}' does NOT exist.")
        print(f"      Create a tag with that name in Clockify or change HOLIDAY_TAG_NAME in the code.")
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
    project_id = find_project_id(ws_id)
    tag_id = find_tag_id(ws_id)
    holiday_tag_id = find_tag_id(ws_id, HOLIDAY_TAG_NAME)
    tz = ZoneInfo(TZ)
    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))

    print("📅 Weekly mode: upload hours from the last day with entries to this week's Friday.")
    print("   (Mon–Fri only; days that already have entries are skipped; Argentina holidays → Holiday.)")
    print()
    desc = input("What did you work on? ").strip() or "Work"
    print()

    last_date = get_last_date_with_entries(ws_id, user_id, project_id)
    start_date = last_date + timedelta(days=1) if last_date else monday_of_week(today)
    end_date = friday_of_week(today)

    if start_date > end_date:
        print("No workdays left in this range.")
        return

    existing_dates = get_dates_with_entries_in_range(ws_id, user_id, start_date, end_date, project_id)
    holidays_set = get_argentina_holidays_in_range(start_date, end_date)

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

    workdays_count = len([d for d in to_create if d not in holidays_set])
    holidays_count = len([d for d in to_create if d in holidays_set])
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
        is_holiday = day in holidays_set
        day_desc = "Holiday" if is_holiday else desc
        t_id = holiday_tag_id if is_holiday else tag_id
        te = create_entry(ws_id, start_utc, end_utc, day_desc, project_id, t_id)
        print(f"[ok] {day} created ({day_desc})")
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
    ap.add_argument("--list-tags", action="store_true", help="List tags and validate holiday tag (Vacation/Holiday)")
    ap.add_argument("--from", dest="from_date", help="Start date YYYY-MM-DD")
    ap.add_argument("--to", dest="to_date", help="End date YYYY-MM-DD")
    ap.add_argument("--desc", help="Description for time entries")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be created without creating entries")
    ap.add_argument("--include-weekends", action="store_true", help="Include Saturdays and Sundays")
    args = ap.parse_args()

    if args.list:
        list_workspaces_and_projects()
        return

    if args.list_tags:
        list_tags_and_validate_holiday()
        return

    # Interactive weekly mode: no --from/--to/--desc → ask description, use last entry date to this week's Friday
    if not args.from_date and not args.to_date and not args.desc:
        run_weekly_interactive()
        return

    if not all([args.from_date, args.to_date, args.desc]):
        ap.error("--from, --to, and --desc are required to create time entries (or run with no args for weekly mode).")

    ws_id = find_workspace_id()
    project_id = find_project_id(ws_id)
    tag_id = find_tag_id(ws_id)
    holiday_tag_id = find_tag_id(ws_id, HOLIDAY_TAG_NAME)
    tz = ZoneInfo(TZ)

    d1, d2 = ymd(args.from_date), ymd(args.to_date)
    holidays_set = get_argentina_holidays_in_range(d1, d2)

    # Compute and show total hours
    workdays, total_hours, hours_per_day = calculate_hours(d1, d2, args.include_weekends)
    holidays_in_scope = sum(1 for d in holidays_set if args.include_weekends or d.weekday() < 5)
    print(f"📅 SUMMARY:")
    print(f"   Range: {d1} → {d2}")
    print(f"   Days to create: {workdays} ({workdays - holidays_in_scope} work + {holidays_in_scope} Argentina holidays)")
    print(f"   Hours per day: {hours_per_day:.2f}h")
    print(f"   Total hours: {total_hours:.2f}h")
    print(f"   Schedule: {START_TIME} - {END_TIME}")
    print(f"   Include weekends: {'Yes' if args.include_weekends else 'No'}")
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

        is_holiday = day in holidays_set
        desc = "Holiday" if is_holiday else args.desc
        t_id = holiday_tag_id if is_holiday else tag_id

        if args.dry_run:
            label = "Holiday" if is_holiday else args.desc
            print(f"[DRY-RUN] {day} | {START_TIME}-{END_TIME} | {label}")
        else:
            te = create_entry(ws_id, start_utc, end_utc, desc, project_id, t_id)
            print(f"[ok] {day} created id={te.get('id')} ({desc})")
        created += 1

    mode = "DRY-RUN (simulated)" if args.dry_run else "real"
    print(f"\nDone. Entries {mode}: {created} | Total hours: {total_hours:.2f}h")

if __name__ == "__main__":
    main()
