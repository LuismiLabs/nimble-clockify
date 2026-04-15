#!/usr/bin/env python3
"""
Non-interactive Clockify helper for OpenClaw agent use.
Place this file in the same directory as main.py (shares the same .env).

Usage:
  python clockify-auto.py status
      Show pending days since last Clockify entry.

  python clockify-auto.py preview --desc "Desarrollo NexStar"
      Show what would be created with a single description for all pending days.

  python clockify-auto.py preview --entries '[{"from":"2026-04-14","to":"2026-04-16","desc":"Bug fixes"},{"from":"2026-04-17","to":"2026-04-18","desc":"Feature dev"}]'
      Show plan with per-range descriptions.

  python clockify-auto.py create --desc "Desarrollo NexStar"
      Create entries (single description for all pending workdays).

  python clockify-auto.py create --entries '[...]'
      Create entries with per-range descriptions.
"""

import argparse
import json
import os
import sys
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests

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
PROJECT_NAME = os.environ.get("CLOCKIFY_PROJECT_NAME", "NexStar")
TAG_NAME = os.environ.get("CLOCKIFY_TAG_NAME", "PHP")
HOLIDAY_TAG_NAME = os.environ.get("CLOCKIFY_HOLIDAY_TAG_NAME", "Vacation/Holiday")
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

def find_project_id(ws_id):
    for p in list_projects(ws_id):
        if p["name"] == PROJECT_NAME:
            return p["id"]
    sys.exit(f'Project "{PROJECT_NAME}" not found.')

def list_tags(ws_id):
    r = requests.get(f"{API}/workspaces/{ws_id}/tags", headers=hdrs(), params={"page-size": 5000})
    r.raise_for_status()
    return r.json()

def find_tag_id(ws_id, tag_name=None):
    name = tag_name if tag_name is not None else TAG_NAME
    for t in list_tags(ws_id):
        if t["name"] == name:
            return t["id"]
    sys.exit(f'Tag "{name}" not found.')

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
    out = set()
    for y in years:
        try:
            r = requests.get(f"{AR_HOLIDAYS_API}/{y}", timeout=10)
            r.raise_for_status()
            for item in r.json():
                d = datetime.strptime(item["fecha"], "%Y-%m-%d").date()
                if d1 <= d <= d2:
                    out.add(d)
        except Exception as e:
            print(f"Warning: could not load Argentina holidays for {y}: {e}", file=sys.stderr)
    return out

def create_entry(ws_id, start_utc, end_utc, description, project_id, tag_id):
    payload = {
        "start": iso(start_utc),
        "end": iso(end_utc),
        "billable": BILLABLE,
        "description": description,
        "projectId": project_id,
        "tagIds": [tag_id],
    }
    r = requests.post(f"{API}/workspaces/{ws_id}/time-entries", headers=hdrs(), json=payload)
    r.raise_for_status()
    return r.json()

# ── Core logic ─────────────────────────────────────────────────────────────────

DAY_NAMES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

def compute_pending_range():
    """Return (start_date, end_date, last_entry_date) for the pending range."""
    today = date.today()
    user = get_user()
    ws_id = find_workspace_id()
    project_id = find_project_id(ws_id)
    last_date = get_last_date_with_entries(ws_id, user["id"], project_id)
    start_date = last_date + timedelta(days=1) if last_date else monday_of_week(today)
    end_date = friday_of_week(today)
    return start_date, end_date, last_date, ws_id, user["id"], project_id

def build_day_list(start_date, end_date, ws_id, user_id, project_id, entries):
    """
    Build list of days to create.
    `entries` is a list of {from, to, desc} dicts (or empty → use same desc for all).
    Returns list of (day, desc, is_holiday).
    """
    existing = get_dates_with_entries_in_range(ws_id, user_id, start_date, end_date, project_id)
    holidays = get_argentina_holidays_in_range(start_date, end_date)

    # Build desc map from entries
    desc_map = {}
    for entry in entries:
        d1 = datetime.strptime(entry["from"], "%Y-%m-%d").date()
        d2 = datetime.strptime(entry["to"], "%Y-%m-%d").date()
        for d in daterange(d1, d2):
            desc_map[d] = entry.get("desc", "Work")

    days = []
    for day in daterange(start_date, end_date):
        if day.weekday() >= 5:  # skip weekends
            continue
        if day in existing:
            continue
        is_holiday = day in holidays
        desc = "Holiday" if is_holiday else desc_map.get(day, None)
        days.append((day, desc, is_holiday))

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
        print("Clockify al día. No hay días pendientes.")
        return

    existing = get_dates_with_entries_in_range(ws_id, user_id, start_date, end_date, project_id)
    holidays = get_argentina_holidays_in_range(start_date, end_date)

    pending = []
    for day in daterange(start_date, end_date):
        if day.weekday() >= 5:
            continue
        if day in existing:
            continue
        pending.append(day)

    if not pending:
        print("Clockify al día. No hay días pendientes.")
        return

    hpd = hours_per_day()
    total_h = len(pending) * hpd

    print(f"Último registro: {last_date or 'ninguno'}")
    print(f"Rango pendiente: {start_date} → {end_date}")
    print(f"Días de trabajo pendientes: {len(pending)}")
    print(f"Horas totales a registrar: {total_h:.2f}h ({hpd:.1f}h/día, {START_TIME}–{END_TIME})")
    print()
    print("Días pendientes:")
    for day in pending:
        tag = " [FERIADO AR]" if day in holidays else ""
        print(f"  {DAY_NAMES[day.weekday()]} {day}{tag}")


def cmd_preview_or_create(mode, desc=None, entries_json=None):
    """mode='preview' or mode='create'"""
    start_date, end_date, last_date, ws_id, user_id, project_id = compute_pending_range()

    if start_date > end_date:
        print("No hay días pendientes. Clockify ya está al día.")
        return

    entries = []
    if entries_json:
        try:
            entries = json.loads(entries_json)
        except json.JSONDecodeError as e:
            sys.exit(f"Error parsing --entries JSON: {e}")
    elif desc:
        # Single description → map to full range
        entries = [{"from": str(start_date), "to": str(end_date), "desc": desc}]
    else:
        sys.exit("Debes pasar --desc o --entries")

    # Validate all days have a description
    days = build_day_list(start_date, end_date, ws_id, user_id, project_id, entries)

    if not days:
        print("Todos los días en el rango ya tienen entradas. Nada que crear.")
        return

    # Check for days without description
    missing_desc = [(day, is_hol) for day, d, is_hol in days if d is None and not is_hol]
    if missing_desc:
        print("ERROR: Faltan descripciones para estos días:")
        for day, _ in missing_desc:
            print(f"  {DAY_NAMES[day.weekday()]} {day}")
        print()
        print("Usa --entries con rangos que cubran todos los días pendientes.")
        sys.exit(1)

    hpd = hours_per_day()
    total_h = len(days) * hpd
    work_days = [(d, desc_, hol) for d, desc_, hol in days if not hol]
    holiday_days = [(d, desc_, hol) for d, desc_, hol in days if hol]

    print(f"{'PREVIEW' if mode == 'preview' else 'CREANDO ENTRADAS'}")
    print(f"{'─' * 40}")
    print(f"Último registro:  {last_date or 'ninguno'}")
    print(f"Rango:            {start_date} → {end_date}")
    print(f"Días a crear:     {len(days)} ({len(work_days)} trabajo + {len(holiday_days)} feriados AR)")
    print(f"Horario:          {START_TIME}–{END_TIME} ({hpd:.1f}h/día)")
    print(f"Total horas:      {total_h:.2f}h")
    print()
    print("Detalle por día:")
    for day, d, is_hol in days:
        label = d if d else "—"
        tag = " [FERIADO]" if is_hol else ""
        print(f"  {DAY_NAMES[day.weekday()]} {day}  →  {label}{tag}")

    if mode == "preview":
        print()
        print("(Preview solamente — usa 'create' para subir las horas)")
        return

    # ── CREATE ──
    tz = ZoneInfo(TZ)
    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))
    tag_id = find_tag_id(ws_id)
    holiday_tag_id = find_tag_id(ws_id, HOLIDAY_TAG_NAME)

    print()
    created = 0
    for day, d, is_hol in days:
        start_local = datetime.combine(day, time(sh, sm), tzinfo=tz)
        end_local = datetime.combine(day, time(eh, em), tzinfo=tz)
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc = end_local.astimezone(ZoneInfo("UTC"))
        t_id = holiday_tag_id if is_hol else tag_id
        create_entry(ws_id, start_utc, end_utc, d, project_id, t_id)
        print(f"  [ok] {day} creado → {d}")
        created += 1

    print()
    print(f"Listo. Entradas creadas: {created} | Total horas: {total_h:.2f}h")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Clockify non-interactive helper for OpenClaw agent.")
    ap.add_argument("command", choices=["status", "preview", "create"], help="Command to run")
    ap.add_argument("--desc", help="Single description for all pending workdays")
    ap.add_argument("--entries", help='JSON array: [{"from":"YYYY-MM-DD","to":"YYYY-MM-DD","desc":"..."}]')
    args = ap.parse_args()

    if args.command == "status":
        cmd_status()
    elif args.command in ("preview", "create"):
        cmd_preview_or_create(args.command, desc=args.desc, entries_json=args.entries)


if __name__ == "__main__":
    main()
