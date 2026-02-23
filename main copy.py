#!/usr/bin/env python3
import argparse
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests

# python main.py --from 2025-08-01 --to 2025-08-31 --desc "Login Radius tickets"

API = "https://api.clockify.me/api/v1"

# 🔑 Coloca aquí tu API Key
API_KEY = "API_KEY"

# ⚙️ Configuración fija
WORKSPACE_NAME = None  # o ponlo si quieres fijar un workspace específico
PROJECT_NAME = "NexStar"
TAG_NAME = "PHP"
TZ = "America/Bogota"
START_TIME = "08:00"
END_TIME = "16:00"
BILLABLE = True

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
        raise SystemExit("No se encontraron Workspaces en tu cuenta.")
    if WORKSPACE_NAME:
        for ws in wss:
            if ws["name"] == WORKSPACE_NAME:
                return ws["id"]
        raise SystemExit(f'Workspace "{WORKSPACE_NAME}" no encontrado.')
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
    raise SystemExit(f'Proyecto "{PROJECT_NAME}" no encontrado en el workspace.')

def list_tags(ws_id):
    r = requests.get(f"{API}/workspaces/{ws_id}/tags",
                     headers=hdrs(), params={"page-size":5000})
    r.raise_for_status()
    return r.json()

def find_tag_id(ws_id):
    for t in list_tags(ws_id):
        if t["name"] == TAG_NAME:
            return t["id"]
    raise SystemExit(f'Tag "{TAG_NAME}" no encontrado en el workspace.')

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

def list_workspaces_and_projects():
    """Lista todos los workspaces y proyectos disponibles con sus IDs."""
    print("🔍 WORKS PACES DISPONIBLES:")
    print("=" * 50)

    workspaces = get_workspaces()
    for i, ws in enumerate(workspaces, 1):
        print(f"{i}. {ws['name']} (ID: {ws['id']})")

        # Listar proyectos de este workspace
        try:
            projects = list_projects(ws['id'])
            if projects:
                print("   📁 Proyectos:")
                for j, proj in enumerate(projects, 1):
                    print(f"      {j}. {proj['name']} (ID: {proj['id']})")
            else:
                print("   📁 Sin proyectos")
        except Exception as e:
            print(f"   ❌ Error al obtener proyectos: {e}")
        print()

    print("🏷️  TAGS DISPONIBLES:")
    print("=" * 50)
    if workspaces:
        try:
            tags = list_tags(workspaces[0]['id'])
            for i, tag in enumerate(tags, 1):
                print(f"{i}. {tag['name']} (ID: {tag['id']})")
        except Exception as e:
            print(f"❌ Error al obtener tags: {e}")

    print("\n💡 Copia los IDs correctos y actualiza las variables en el código:")
    print(f"   WORKSPACE_NAME = 'nombre_del_workspace'  # o None para usar el primero")
    print(f"   PROJECT_NAME = 'nombre_del_proyecto'")
    print(f"   TAG_NAME = 'nombre_del_tag'")

def calculate_hours(d1: date, d2: date):
    """Calcula el total de horas laborables en el rango de fechas."""
    total_hours = 0
    workdays = 0

    for day in daterange(d1, d2):
        if day.weekday() >= 5:  # salta sábados y domingos
            continue
        workdays += 1

    # Calcular horas por día
    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))
    hours_per_day = (eh - sh) + (em - sm) / 60

    total_hours = workdays * hours_per_day

    return workdays, total_hours, hours_per_day

def main():
    ap = argparse.ArgumentParser(description="Carga horas L–V en Clockify.")
    ap.add_argument("--list", action="store_true", help="Lista workspaces, proyectos y tags disponibles")
    ap.add_argument("--from", dest="from_date", help="Fecha inicio YYYY-MM-DD")
    ap.add_argument("--to", dest="to_date", help="Fecha fin YYYY-MM-DD")
    ap.add_argument("--desc", help="Descripción de las entradas")
    ap.add_argument("--dry-run", action="store_true", help="Muestra qué se crearía sin crear entradas reales")
    args = ap.parse_args()

    if args.list:
        list_workspaces_and_projects()
        return

    # Validar que se proporcionen los argumentos requeridos para crear entradas
    if not all([args.from_date, args.to_date, args.desc]):
        ap.error("Los argumentos --from, --to y --desc son requeridos para crear entradas de tiempo.")

    ws_id = find_workspace_id()
    project_id = find_project_id(ws_id)
    tag_id = find_tag_id(ws_id)
    tz = ZoneInfo(TZ)

    d1, d2 = ymd(args.from_date), ymd(args.to_date)

    # Calcular y mostrar horas totales
    workdays, total_hours, hours_per_day = calculate_hours(d1, d2)
    print(f"📅 RESUMEN:")
    print(f"   Rango: {d1} → {d2}")
    print(f"   Días laborables: {workdays}")
    print(f"   Horas por día: {hours_per_day:.2f}h")
    print(f"   Total de horas: {total_hours:.2f}h")
    print(f"   Horario: {START_TIME} - {END_TIME}")
    print()

    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))

    created = 0
    for day in daterange(d1, d2):
        if day.weekday() >= 5:  # salta sábados y domingos
            continue

        start_local = datetime.combine(day, time(sh, sm), tzinfo=tz)
        end_local   = datetime.combine(day, time(eh, em), tzinfo=tz)
        start_utc = start_local.astimezone(ZoneInfo("UTC"))
        end_utc   = end_local.astimezone(ZoneInfo("UTC"))

        if args.dry_run:
            print(f"[DRY-RUN] {day} | {START_TIME}-{END_TIME} | {args.desc}")
        else:
            te = create_entry(ws_id, start_utc, end_utc, args.desc, project_id, tag_id)
            print(f"[ok] {day} creado id={te.get('id')}")
        created += 1

    mode = "DRY-RUN (simulado)" if args.dry_run else "real"
    print(f"\nHecho. Entradas {mode}: {created} | Total horas: {total_hours:.2f}h")

if __name__ == "__main__":
    main()
