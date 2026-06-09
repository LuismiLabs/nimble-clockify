"""Shared Clockify helpers: clients, projects, activities (tasks), tag inference."""

import os
import re

API = "https://api.clockify.me/api/v1"

NIMBLE_TAGS = {
    "vacation": "Vacation",
    "holiday": "Holiday",
    "personal": "Personal",
    "overtime": "Additional Work (Authorized Overtime)",
}

VACATION_KEYWORDS = ("vacation", "vacaciones", "annual leave", "pto day", "paid time off", "day off")
PERSONAL_KEYWORDS = ("sick", "enfermo", "doctor", "medical", "personal day", "personal leave", "family")
OVERTIME_KEYWORDS = ("overtime", "extra hours", "authorized overtime", "additional work")
MEETING_KEYWORDS = ("meeting", "standup", "demo", "call", "sync", "huddle", "retro", "planning")
OTHER_KEYWORDS = ("other activity", "activity: other", "misc", "admin")


def infer_tag(desc=None, is_holiday=False, explicit=None):
    """Guess the Nimble tag from context. Returns tag name or None."""
    if explicit:
        return explicit
    if is_holiday:
        return NIMBLE_TAGS["holiday"]
    if not desc:
        return None
    text = desc.lower()
    if any(k in text for k in OVERTIME_KEYWORDS):
        return NIMBLE_TAGS["overtime"]
    if any(k in text for k in PERSONAL_KEYWORDS):
        return NIMBLE_TAGS["personal"]
    if any(k in text for k in VACATION_KEYWORDS):
        return NIMBLE_TAGS["vacation"]
    return None


def infer_activity(desc=None, is_holiday=False, is_pto=False, explicit=None, default="Working Time", pto_name="PTO"):
    """Guess the Clockify activity (task name). Returns activity name."""
    if explicit:
        return explicit
    if is_holiday or is_pto:
        return pto_name
    if not desc:
        return default
    text = desc.lower()
    if any(k in text for k in MEETING_KEYWORDS):
        return "Meetings"
    if any(k in text for k in OTHER_KEYWORDS) or re.search(r"\bother\b", text):
        return "Other"
    return default


def needs_pto_activity(tag_name):
    return tag_name in (NIMBLE_TAGS["vacation"], NIMBLE_TAGS["holiday"], NIMBLE_TAGS["personal"])


def list_clients(ws_id, hdrs_fn, requests_mod):
    r = requests_mod.get(f"{API}/workspaces/{ws_id}/clients", headers=hdrs_fn(), params={"page-size": 5000})
    r.raise_for_status()
    return r.json()


def list_tasks(ws_id, project_id, hdrs_fn, requests_mod):
    r = requests_mod.get(
        f"{API}/workspaces/{ws_id}/projects/{project_id}/tasks",
        headers=hdrs_fn(),
        params={"page-size": 5000},
    )
    r.raise_for_status()
    return r.json()


def client_name_map(ws_id, hdrs_fn, requests_mod):
    return {c["id"]: c["name"] for c in list_clients(ws_id, hdrs_fn, requests_mod)}


def find_project_id(ws_id, hdrs_fn, requests_mod, list_projects_fn, project_name, client_name=None):
    clients = client_name_map(ws_id, hdrs_fn, requests_mod) if client_name else {}
    for p in list_projects_fn(ws_id):
        if p["name"] != project_name:
            continue
        if client_name:
            cname = clients.get(p.get("clientId"), "")
            if client_name.lower() not in cname.lower():
                continue
        return p["id"]
    hint = f' (client "{client_name}")' if client_name else ""
    raise SystemExit(f'Project "{project_name}"{hint} not found.')


def find_task_id(ws_id, project_id, task_name, hdrs_fn, requests_mod, required=True):
    if not task_name:
        return None
    for t in list_tasks(ws_id, project_id, hdrs_fn, requests_mod):
        if t["name"] == task_name:
            return t["id"]
    if required:
        raise SystemExit(f'Activity "{task_name}" not found on project.')
    return None


def find_tag_id(ws_id, tag_name, list_tags_fn, required=True):
    if not tag_name:
        return None
    for t in list_tags_fn(ws_id):
        if t["name"] == tag_name:
            return t["id"]
    if required:
        raise SystemExit(f'Tag "{tag_name}" not found in the workspace.')
    return None


def create_entry_payload(start_iso, end_iso, description, project_id, tag_ids=None, task_id=None, billable=True):
    payload = {
        "start": start_iso,
        "end": end_iso,
        "billable": billable,
        "description": description,
        "projectId": project_id,
    }
    if task_id:
        payload["taskId"] = task_id
    if tag_ids:
        payload["tagIds"] = tag_ids
    return payload


def project_client_names(ws_id, project_id, hdrs_fn, requests_mod, list_projects_fn):
    """Return (client_name, project_name) for a project id."""
    clients = client_name_map(ws_id, hdrs_fn, requests_mod)
    for p in list_projects_fn(ws_id):
        if p["id"] == project_id:
            cname = clients.get(p.get("clientId"), "(no client)")
            return cname, p["name"]
    return "(unknown client)", "(unknown project)"
