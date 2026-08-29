from __future__ import annotations

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

from app.db.models import Base

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "db" / "schema.sql"

HEADER = (
    "-- GENERATED FILE -- DO NOT EDIT BY HAND. "
    "Rendered from models.py via dump_schema.py.\n"
)


def main() -> None:
    dialect = postgresql.dialect()
    parts = [HEADER.rstrip() + f" Generated {datetime.date.today().isoformat()}.\n"]

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
