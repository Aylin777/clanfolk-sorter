# Clanfolk Sorter

An unofficial command-line helper for ranking Clanfolk skills and finding suitable clan members for different tasks.

## Setup

From the project directory, create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
python -m pip install -r requirements.txt
```

## Quick start

Initialize the database:

```bash
python cli.py init
```

Add some skills:

```bash
python cli.py skill add Farming
python cli.py skill add Mining
python cli.py skill add Cooking
python cli.py skill list
```

Add a folk using the IDs of their loved and hated skills:

```bash
python cli.py folk add "Aila" 1 2
```

This example assumes Farming has ID `1` and Mining has ID `2`. Check the skill list before choosing IDs.

List your folks and note the new folk’s ID:

```bash
python cli.py folk list
```

Enter skill levels and aptitudes interactively:

```bash
python cli.py rel add 1 --interactive
```

Leave a level blank to skip a skill. Aptitude values range from `0` to `4`.

**Skipping does not mean level zero, it won't record a skill.** 
Unrecorded skills are excluded from both individual and clan-wide rankings. 
If a record already exists, skipping leaves it unchanged and it still participates in rankings (except hated skills in clan-wide results). 
Use `rel update` to change an existing record. An explicitly recorded level of `0` does participate.

Alternatively, add one relation without prompts (`folk_id skill_id level aptitude`):

```bash
python cli.py rel add 1 1 5 2
python cli.py rel update 1 1 --level 6
```

Names are trimmed and cannot be blank (maximum 20 characters for skills, 50 for folks). 
Loved and hated skills must be different and must exist. 
Levels must be between zero and the aptitude maximum: `0 → 5`, `1 → 10`, `2 → 12`, `3 → 14`, `4 → 15`.
Out-of-range levels are rejected. When lowering aptitude, also provide a valid `--level` if the existing level exceeds the new maximum.

View skill priorities for that folk:

```bash
python cli.py folk sort 1
```

View the top candidates for each skill across your clan:

```bash
python cli.py clan status
```

For more commands and options use `--help` flag.

## How ranking works

Higher scores mean higher priority. The scoring considers:

- current skill level
- aptitude
- bonus for loved skills
- penalty for hated skills
- small bonus for being near the maximum skill level (ie. folk with 4/5 is still more useful in short run than folk with 1/12)

Hated skills are excluded from clan-wide candidate lists.

Scores are suggestions based on custom heuristics, not official game rules. Clan-wide output ranks candidates independently for each skill; it does not create an optimized work schedule. Yet.

## Data storage

The application stores data in a local SQLite file named `clanfolksorter.db`.

The database is always stored in the cloned repository root, beside `database.py`, regardless of your current working directory. 
The path is resolved from the source file, so each clone has its own database. 
Database files remain ignored by Git; they are not included when cloning. Back up this file to preserve your data.

### Upgrading an existing database

`init` creates new databases; it does not silently change an old schema. For a
database created by an earlier version, place it in the repository root and run
from that root:

```bash
python cli.py migrate
```

This creates a uniquely named `clanfolksorter.backup-<id>.db` SQLite backup before
rebuilding the tables.

Command failures write errors to stderr and return a nonzero exit code. Ctrl+C
returns `130`; end-of-input returns `1`. Interactive entry saves each relation
individually, so completed entries remain saved after cancellation or failure.

### Regression tests

```bash
python -m unittest discover -s tests -v
```

Tests use temporary databases and do not modify your personal database.

## Project status

This is a very early-stage personal project. Built out of frustration over fixing clan priorities during gameplay after first winter hit author of this project like a brick.

Data entry is manual - there is no game-save import or in-game integration or plans to do so in the nearest future.

Plans for the future include:
- expanding test coverage (bare minimum exists)
- automating testing (don't do it yourself)
- automate populating DB with skills (those don't change)
- prettify and simplify usage of this project (script launch, DB init)

## Disclaimer

This project is not affiliated with or endorsed by the developers of Clanfolk.

## License

Licensed under the MIT License.
