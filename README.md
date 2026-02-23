# Clockify – Carga de horas L–V con feriados Argentina

Script en Python para cargar horas en [Clockify](https://clockify.me/) de lunes a viernes (o todos los días con opción), marcando automáticamente los **feriados argentinos** como "Holiday" con un tag de vacaciones.

## Requisitos

- Python 3.10+ (usa `zoneinfo`)
- Dependencia: `requests`

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install requests
```

## Configuración

1. **API Key de Clockify**  
   En [Clockify → Profile → API](https://clockify.me/user/settings) genera una API key.  
   - Opción A: Pégala en `main.py` en `API_KEY = "..."`.  
   - Opción B (recomendada): no la pongas en el código y usa variable de entorno:
     ```bash
     export CLOCKIFY_API_KEY="tu_api_key"
     ```
   El script usa la variable de entorno si está definida.

2. **Workspace, proyecto y tags**  
   Edita al inicio de `main.py`:
   - `WORKSPACE_NAME`: nombre del workspace o `None` para usar el primero.
   - `PROJECT_NAME`: nombre del proyecto (ej. `"NexStar"`).
   - `TAG_NAME`: tag para trabajo normal (ej. `"PHP"`).
   - `HOLIDAY_TAG_NAME`: tag para feriados (ej. `"Vacation/Holiday"`). Debe existir en Clockify.
   - `TZ`, `START_TIME`, `END_TIME`: zona horaria y horario de la entrada (ej. 08:00–16:00).

Para ver nombres e IDs correctos:

```bash
python main.py --list
python main.py --list-tags
```

`--list-tags` además valida que exista el tag de feriados (`HOLIDAY_TAG_NAME`).

## Comandos

| Comando | Descripción |
|--------|-------------|
| `python main.py --list` | Lista workspaces, proyectos y tags (para configurar nombres/IDs). |
| `python main.py --list-tags` | Lista tags y comprueba que exista el tag de feriados. |
| `python main.py --from YYYY-MM-DD --to YYYY-MM-DD --desc "Texto"` | Carga horas en el rango (solo L–V, feriados AR como Holiday). |
| `python main.py --from ... --to ... --desc "..." --dry-run` | Simula: muestra qué se crearía sin llamar a la API. |
| `python main.py --from ... --to ... --desc "..." --include-weekends` | Incluye sábados y domingos en la carga. |

### Ejemplos

```bash
# Simular enero 2025
python main.py --from 2025-01-01 --to 2025-01-31 --desc "Desarrollo PHP" --dry-run

# Cargar horas de verdad
python main.py --from 2025-01-01 --to 2025-01-31 --desc "Desarrollo PHP"
```

## Feriados Argentina

Se usa la API pública [ArgentinaDatos](https://api.argentinadatos.com/v1/feriados) (sin API key).  
Para cada día del rango:

- Si es **feriado argentino** → se crea la entrada con descripción **"Holiday"** y el tag configurado en `HOLIDAY_TAG_NAME` (ej. `Vacation/Holiday`).
- Si no es feriado → se usa tu `--desc` y el tag `TAG_NAME` (ej. `PHP`).

Solo se procesan lunes a viernes salvo que uses `--include-weekends`.

## Resumen en consola

Antes de crear entradas se muestra un resumen con:

- Rango de fechas
- Días a cargar (trabajo + feriados AR)
- Horas por día y total
- Si se incluyen fines de semana

## Estructura del repo

```
clock/
├── main.py      # Script principal
├── README.md    # Esta documentación
├── .gitignore   # Ignora venv, __pycache__, .env, etc.
└── venv/        # Entorno virtual (ignorado por git)
```

## Seguridad

- No subas tu API key a un repo público. Usa `CLOCKIFY_API_KEY` en el entorno o un archivo local que esté en `.gitignore` (ej. `.env`).
