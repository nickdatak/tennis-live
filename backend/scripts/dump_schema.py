"""Regenerate backend/app/db/schema.sql from the ORM models.

Usage: python3 backend/scripts/dump_schema.py

schema.sql used to be maintained by hand alongside models.py -- two definitions
of the same thing, guaranteed to drift. It is now DERIVED: models.py is the
single source of truth and this script renders it as Postgres DDL. Rerun after
changing any model, and never edit schema.sql directly.

Touches no database; it only reads the model metadata and writes a file.
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.models import Base

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql"

HEADER = """\
-- GENERATED FILE -- DO NOT EDIT BY HAND.
-- Rendered from backend/app/db/models.py, which is the single source of truth.
-- Regenerate with: python3 backend/scripts/dump_schema.py
--
-- Run this once against a fresh Supabase project. The application never issues
-- DDL: it holds a read-only role and only verifies that these tables exist.
-- Note that CREATE TABLE IF NOT EXISTS only ever ADDS -- it will not drop a
-- table you removed from the models, nor alter a column you changed.
"""


def main() -> None:
    dialect = postgresql.dialect()
    parts = [HEADER, f"-- Generated {datetime.date.today().isoformat()}\n"]

    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table, if_not_exists=True).compile(dialect=dialect)).strip()
        parts.append(f"\n{ddl};\n")
        for index in sorted(table.indexes, key=lambda i: i.name or ""):
            idx = str(CreateIndex(index, if_not_exists=True).compile(dialect=dialect)).strip()
            parts.append(f"{idx};\n")

    OUTPUT.write_text("".join(parts))
    print(f"Wrote {OUTPUT.relative_to(Path.cwd()) if OUTPUT.is_relative_to(Path.cwd()) else OUTPUT}")
    print(f"  {len(Base.metadata.sorted_tables)} tables, "
          f"{sum(len(t.indexes) for t in Base.metadata.sorted_tables)} indexes")


if __name__ == "__main__":
    main()
