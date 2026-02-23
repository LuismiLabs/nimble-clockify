#!/usr/bin/env python3
import argparse
import os
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
import requests

# Cargar .env si existe (para CLOCKIFY_API_KEY sin exportar a mano)
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

# 🔑 API Key: variable de entorno CLOCKIFY_API_KEY o archivo .env (no commitear la key real)
API_KEY = os.environ.get("CLOCKIFY_API_KEY", "PON_AQUI_TU_API_KEY")

# ⚙️ Configuración fija
WORKSPACE_NAME = None  # o ponlo si quieres fijar un workspace específico
PROJECT_NAME = "NexStar"
TAG_NAME = "PHP"
HOLIDAY_TAG_NAME = "Vacation/Holiday"  # tag para días feriados (Argentina)
TZ = "America/Bogota"
START_TIME = "08:00"
END_TIME = "16:00"
BILLABLE = True

# API feriados Argentina (sin API key)
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

def find_tag_id(ws_id, tag_name=None):
    name = tag_name if tag_name is not None else TAG_NAME
    for t in list_tags(ws_id):
        if t["name"] == name:
            return t["id"]
    raise SystemExit(f'Tag "{name}" no encontrado en el workspace.')

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
    """Obtiene time entries del usuario en el workspace en el rango [start_utc, end_utc]."""
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
    """Extrae la fecha (date) del inicio de una time entry."""
    s = entry.get("timeInterval", {}).get("start") or entry.get("start")
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).date()

def get_last_date_with_entries(ws_id, user_id, project_id=None):
    """
    Devuelve la última fecha (date) en que el usuario tiene al menos una entrada en este proyecto/workspace.
    Si no hay ninguna entrada, devuelve None.
    """
    tz_utc = ZoneInfo("UTC")
    end_utc = datetime.now(tz_utc)
    start_utc = end_utc - timedelta(days=400)
    entries = get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id)
    dates = [_entry_start_date(e) for e in entries if _entry_start_date(e)]
    return max(dates) if dates else None

def get_dates_with_entries_in_range(ws_id, user_id, d1, d2, project_id=None):
    """Devuelve un set de fechas que ya tienen al menos una entrada en [d1, d2]."""
    tz_utc = ZoneInfo("UTC")
    start_utc = datetime.combine(d1, time(0, 0), tzinfo=tz_utc)
    end_utc = datetime.combine(d2, time(23, 59, 59), tzinfo=tz_utc)
    entries = get_user_time_entries(ws_id, user_id, start_utc, end_utc, project_id)
    return {_entry_start_date(e) for e in entries if _entry_start_date(e)}

def friday_of_week(d: date):
    """Viernes de la semana que contiene d. Si d es sáb/dom, es el viernes ya pasado."""
    w = d.weekday()
    if w <= 4:
        return d + timedelta(days=4 - w)
    return d - timedelta(days=w - 4)

def monday_of_week(d: date):
    """Lunes de la semana que contiene d."""
    return d - timedelta(days=d.weekday())

def get_argentina_holidays(year: int):
    """Obtiene feriados de Argentina para un año (API ArgentinaDatos, sin API key)."""
    r = requests.get(f"{AR_HOLIDAYS_API}/{year}", timeout=10)
    r.raise_for_status()
    data = r.json()
    return [datetime.strptime(item["fecha"], "%Y-%m-%d").date() for item in data]

def get_argentina_holidays_in_range(d1: date, d2: date):
    """Devuelve un set de fechas que son feriados argentinos en [d1, d2]."""
    years = {d1.year, d2.year}
    out = set()
    for y in years:
        try:
            for d in get_argentina_holidays(y):
                if d1 <= d <= d2:
                    out.add(d)
        except requests.RequestException as e:
            raise SystemExit(f"No se pudieron cargar feriados Argentina ({y}): {e}")
    return out

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
    print(f"   HOLIDAY_TAG_NAME = 'nombre_del_tag_feriados'  # ej: Vacation/Holiday")

def list_tags_and_validate_holiday():
    """Lista todos los tags del workspace y valida que exista el tag de feriados."""
    ws_id = find_workspace_id()
    print("🏷️  TAGS DISPONIBLES EN TU WORKSPACE:")
    print("=" * 50)
    tags = list_tags(ws_id)
    for i, t in enumerate(tags, 1):
        mark = " ← feriados" if t["name"] == HOLIDAY_TAG_NAME else ""
        print(f"   {i}. {t['name']} (ID: {t['id']}){mark}")
    print()
    # Validar tag de feriados
    found = any(t["name"] == HOLIDAY_TAG_NAME for t in tags)
    if found:
        print(f"   ✅ Tag para feriados '{HOLIDAY_TAG_NAME}' encontrado.")
    else:
        print(f"   ❌ Tag para feriados '{HOLIDAY_TAG_NAME}' NO existe.")
        print(f"      Crea un tag con ese nombre en Clockify o cambia HOLIDAY_TAG_NAME en el código.")
    print()

def run_weekly_interactive():
    """
    Modo semanal: pide la descripción, calcula desde el día siguiente al último con horas
    hasta el viernes de esta semana, y crea entradas solo para los días que aún no tienen
    (L–V; feriados AR con tag Holiday).
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

    print("📅 Modo semanal: subir horas desde el último día cargado hasta el viernes de esta semana.")
    print("   (Solo L–V; los días que ya tienen horas se omiten; feriados AR → Holiday.)")
    print()
    desc = input("¿En qué trabajaste? ").strip() or "Trabajo"
    print()

    last_date = get_last_date_with_entries(ws_id, user_id, project_id)
    start_date = last_date + timedelta(days=1) if last_date else monday_of_week(today)
    end_date = friday_of_week(today)

    if start_date > end_date:
        print("No hay días laborables pendientes en este rango.")
        return

    existing_dates = get_dates_with_entries_in_range(ws_id, user_id, start_date, end_date, project_id)
    holidays_set = get_argentina_holidays_in_range(start_date, end_date)

    # Días a crear: weekdays en [start_date, end_date] que no están en existing_dates
    to_create = []
    for day in daterange(start_date, end_date):
        if day.weekday() >= 5:
            continue
        if day in existing_dates:
            continue
        to_create.append(day)

    if not to_create:
        print("Todos los días laborables en el rango ya tienen horas cargadas. Nada que crear.")
        return

    workdays_count = len([d for d in to_create if d not in holidays_set])
    holidays_count = len([d for d in to_create if d in holidays_set])
    hours_per_day = (eh - sh) + (em - sm) / 60
    total_hours = len(to_create) * hours_per_day

    print(f"📅 RESUMEN:")
    print(f"   Último día con horas: {last_date or 'ninguno'}")
    print(f"   Rango a cargar: {start_date} → {end_date}")
    print(f"   Días a crear: {len(to_create)} ({workdays_count} trabajo + {holidays_count} feriados AR)")
    print(f"   Descripción (trabajo): {desc}")
    print(f"   Total horas: {total_hours:.2f}h")
    print()

    confirm = input("¿Crear estas entradas? [s/N]: ").strip().lower()
    if confirm not in ("s", "si", "sí", "y", "yes"):
        print("Cancelado.")
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
        print(f"[ok] {day} creado ({day_desc})")
        created += 1

    print(f"\nHecho. Entradas creadas: {created} | Total horas: {total_hours:.2f}h")

def calculate_hours(d1: date, d2: date, include_weekends=False):
    """Calcula el total de horas laborables en el rango de fechas."""
    total_hours = 0
    workdays = 0

    for day in daterange(d1, d2):
        if not include_weekends and day.weekday() >= 5:  # salta sábados y domingos
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
    ap.add_argument("--list-tags", action="store_true", help="Lista tags y valida que exista el tag de feriados (Vacation/Holiday)")
    ap.add_argument("--from", dest="from_date", help="Fecha inicio YYYY-MM-DD")
    ap.add_argument("--to", dest="to_date", help="Fecha fin YYYY-MM-DD")
    ap.add_argument("--desc", help="Descripción de las entradas")
    ap.add_argument("--dry-run", action="store_true", help="Muestra qué se crearía sin crear entradas reales")
    ap.add_argument("--include-weekends", action="store_true", help="Incluye sábados y domingos en las entradas")
    args = ap.parse_args()

    if args.list:
        list_workspaces_and_projects()
        return

    if args.list_tags:
        list_tags_and_validate_holiday()
        return

    # Modo semanal interactivo: sin --from/--to/--desc → pregunta descripción y usa desde último día con horas hasta el viernes de esta semana
    if not args.from_date and not args.to_date and not args.desc:
        run_weekly_interactive()
        return

    # Validar que se proporcionen los argumentos requeridos para crear entradas
    if not all([args.from_date, args.to_date, args.desc]):
        ap.error("Los argumentos --from, --to y --desc son requeridos para crear entradas de tiempo (o ejecuta sin argumentos para el modo semanal).")

    ws_id = find_workspace_id()
    project_id = find_project_id(ws_id)
    tag_id = find_tag_id(ws_id)
    holiday_tag_id = find_tag_id(ws_id, HOLIDAY_TAG_NAME)
    tz = ZoneInfo(TZ)

    d1, d2 = ymd(args.from_date), ymd(args.to_date)
    holidays_set = get_argentina_holidays_in_range(d1, d2)

    # Calcular y mostrar horas totales
    workdays, total_hours, hours_per_day = calculate_hours(d1, d2, args.include_weekends)
    # Feriados que caen en días que vamos a procesar
    holidays_in_scope = sum(1 for d in holidays_set if args.include_weekends or d.weekday() < 5)
    print(f"📅 RESUMEN:")
    print(f"   Rango: {d1} → {d2}")
    print(f"   Días a cargar: {workdays} ({workdays - holidays_in_scope} trabajo + {holidays_in_scope} feriados AR)")
    print(f"   Horas por día: {hours_per_day:.2f}h")
    print(f"   Total de horas: {total_hours:.2f}h")
    print(f"   Horario: {START_TIME} - {END_TIME}")
    print(f"   Incluye fines de semana: {'Sí' if args.include_weekends else 'No'}")
    print()

    sh, sm = map(int, START_TIME.split(":"))
    eh, em = map(int, END_TIME.split(":"))

    created = 0
    for day in daterange(d1, d2):
        if not args.include_weekends and day.weekday() >= 5:  # salta sábados y domingos
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
            print(f"[ok] {day} creado id={te.get('id')} ({desc})")
        created += 1

    mode = "DRY-RUN (simulado)" if args.dry_run else "real"
    print(f"\nHecho. Entradas {mode}: {created} | Total horas: {total_hours:.2f}h")

if __name__ == "__main__":
    main()
