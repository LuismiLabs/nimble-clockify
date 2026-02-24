# Clockify – Log Mon–Fri hours with Argentina holidays

Python script to log hours to [Clockify](https://clockify.me/) for weekdays (Mon–Fri), or all days with an option. It automatically marks **Argentina public holidays** as "Holiday" with a vacation tag.

## Requirements

- Python 3.10+ (uses `zoneinfo`)
- Dependency: `requests`

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install requests
```

## Setup

1. **Environment file (`.env`)**

   There is a template in `.env.example`. To get started:

   ```bash
   cp .env.example .env
   ```

   Then edit `.env` and fill in your values:

   ```env
   CLOCKIFY_API_KEY=your_clockify_api_key_here

   # Optional: workspace and project configuration
   # If CLOCKIFY_WORKSPACE_NAME is empty, the first workspace will be used.
   CLOCKIFY_WORKSPACE_NAME=Your Workspace Name
   CLOCKIFY_PROJECT_NAME=NexStar
   CLOCKIFY_TAG_NAME=PHP
   CLOCKIFY_HOLIDAY_TAG_NAME=Vacation/Holiday

   # Timezone and working hours
   CLOCKIFY_TZ=America/Bogota
   CLOCKIFY_START_TIME=08:00
   CLOCKIFY_END_TIME=16:00
   ```

   The script automatically loads `.env` on startup, so you don’t need to export these manually.

2. **Configure via env vars (optional)**

   If you prefer, you can set any of these as real env vars instead of using `.env`, for example:

   ```bash
   export CLOCKIFY_API_KEY="your_key"
   export CLOCKIFY_PROJECT_NAME="NexStar"
   ```

   Env vars override the defaults in `main.py`.

To see the correct names and IDs:

```bash
python main.py --list
python main.py --list-tags
```

`--list-tags` also checks that the holiday tag (`HOLIDAY_TAG_NAME`) exists.

## Global command: `clockify-nimble`

To run the script from any directory without `cd`-ing into the project:

1. Add the wrapper to your PATH (once):

   ```bash
   cd /path/to/clock
   ln -sf "$(pwd)/bin/clockify-nimble" /usr/local/bin/clockify-nimble
   ```

   Or use `~/bin`:

   ```bash
   mkdir -p ~/bin
   ln -sf "$(pwd)/bin/clockify-nimble" ~/bin/clockify-nimble
   ```

   Ensure `~/bin` is in your PATH (e.g. in `~/.zshrc`: `export PATH="$HOME/bin:$PATH"`).

2. From any terminal:

   ```bash
   clockify-nimble              # weekly mode (asks for description)
   clockify-nimble --list-tags  # list tags
   clockify-nimble --from 2025-01-01 --to 2025-01-31 --desc "Work" --dry-run
   ```

The wrapper uses the project’s `venv` or `.venv` and the project’s `.env`, so you don’t need to activate the env or be in the repo folder.

## Commands

| Command | Description |
|--------|-------------|
| `python main.py` | **Weekly mode**: asks for description, creates entries from the last day with hours to this week’s Friday (Mon–Fri only, skips days that already have entries; Argentina holidays → Holiday). |
| `python main.py --list` | List workspaces, projects, and tags (to configure names/IDs). |
| `python main.py --list-tags` | List tags and validate that the holiday tag exists. |
| `python main.py --from YYYY-MM-DD --to YYYY-MM-DD --desc "Text"` | Create entries in the given range (Mon–Fri only; Argentina holidays as Holiday). |
| `python main.py --from ... --to ... --desc "..." --dry-run` | Dry run: show what would be created without calling the API. |
| `python main.py --from ... --to ... --desc "..." --include-weekends` | Include Saturdays and Sundays. |

### Examples

```bash
# Weekly mode (e.g. every Friday): just run and answer "What did you work on?"
python main.py

# Dry run for January 2025
python main.py --from 2025-01-01 --to 2025-01-31 --desc "PHP development" --dry-run

# Actually create entries for a range
python main.py --from 2025-01-01 --to 2025-01-31 --desc "PHP development"
```

## Argentina holidays

The script uses the public [ArgentinaDatos](https://api.argentinadatos.com/v1/feriados) API (no API key). For each day in the range:

- If it’s an **Argentina public holiday** → the entry is created with description **"Holiday"** and the tag set in `HOLIDAY_TAG_NAME` (e.g. `Vacation/Holiday`).
- Otherwise → your `--desc` and `TAG_NAME` (e.g. `PHP`) are used.

Only weekdays are processed unless you use `--include-weekends`.

## Weekly mode (recommended on Fridays)

If you run the script **with no arguments** (`python main.py`):

1. It asks: **What did you work on?** (that description is used for work days).
2. It finds in Clockify the **last day** you already have entries for in this project.
3. It uses the **next day** as start and **this week’s Friday** as end.
4. Of those days, it only considers **Mon–Fri** and **skips days that already have entries** (no duplicates).
5. For each day to create: if it’s an **Argentina holiday** → description "Holiday" and Vacation/Holiday tag; otherwise → your description and the normal tag (e.g. PHP).
6. It shows a summary and asks for confirmation (**Create these entries? [y/N]**) before creating.

So you can run the script every Friday, answer what you worked on, and upload only the missing week without touching dates or duplicating days.

## Console summary

Before creating entries, a summary is shown with:

- Date range
- Days to create (work + Argentina holidays)
- Hours per day and total
- Whether weekends are included

## Repo structure

```
clock/
├── bin/
│   └── clockify-nimble   # Wrapper for global command
├── main.py               # Main script
├── README.md             # This documentation
├── .gitignore            # Ignores venv, __pycache__, .env, etc.
└── venv/ or .venv/       # Virtual env (ignored by git)
```

## Security

- Do not commit your API key to a public repo. Use the `CLOCKIFY_API_KEY` env var or a local file listed in `.gitignore` (e.g. `.env`).
