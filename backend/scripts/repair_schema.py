"""One-off repair for a database created by the old create_all() path.

An earlier version of the app created tables at startup as a convenience.
create_all() creates missing tables but never alters existing ones, so a
database could end up with the newest tables present, an older column set, and
an alembic_version that had not moved. This reconciles that state without
losing the data already in it.

    python -m scripts.repair_schema            # report only
    python -m scripts.repair_schema --apply    # make the changes
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings  # noqa: E402

# (table, column, DDL type) for columns added by migrations after the initial one.
EXPECTED_COLUMNS = [
    ("patient_profiles", "height_cm", "FLOAT"),
    ("patient_profiles", "sex_at_birth", "VARCHAR(20)"),
]
HEAD_REVISION = "1926a9f65cfe"


def sqlite_path() -> Path:
    url = settings.DATABASE_URL
    if "sqlite" not in url:
        raise SystemExit("This repair script only handles the SQLite development database.")
    return Path(url.split("///")[-1]).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Perform the repair.")
    args = parser.parse_args()

    path = sqlite_path()
    if not path.exists():
        print(f"No database at {path}. Run `alembic upgrade head` to create one.")
        return 1

    conn = sqlite3.connect(path)
    tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
    version = [r[0] for r in conn.execute("select version_num from alembic_version")] \
        if "alembic_version" in tables else []

    print(f"database:        {path}")
    print(f"alembic version: {version or 'none'}")
    print(f"tables:          {len(tables)}")

    missing = []
    for table, column, ddl in EXPECTED_COLUMNS:
        if table not in tables:
            continue
        columns = {r[1] for r in conn.execute(f"pragma table_info({table})")}
        if column not in columns:
            missing.append((table, column, ddl))

    if not missing and version == [HEAD_REVISION]:
        print("\nNothing to repair.")
        return 0

    print("\nWould apply:")
    for table, column, ddl in missing:
        print(f"  ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    if version != [HEAD_REVISION]:
        print(f"  UPDATE alembic_version SET version_num = '{HEAD_REVISION}'")

    if not args.apply:
        print("\nRe-run with --apply to make these changes.")
        return 0

    for table, column, ddl in missing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
    if version:
        conn.execute("UPDATE alembic_version SET version_num = ?", (HEAD_REVISION,))
    else:
        conn.execute("INSERT INTO alembic_version (version_num) VALUES (?)", (HEAD_REVISION,))
    conn.commit()
    print("\nRepaired. Verify with `alembic check`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
