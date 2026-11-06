#!/usr/bin/env bash
set -euo pipefail
pip install -q sqlalchemy==2.0.36 alembic==1.14.0 psycopg2-binary pydantic pydantic-settings email-validator greenlet
alembic upgrade head
python - <<'PY'
from sqlalchemy import create_engine, text
e = create_engine("postgresql+psycopg2://docchat:docchat@postgres:5432/docchat")
with e.connect() as c:
    tables = c.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")).fetchall()
    print("tables", [t[0] for t in tables])
PY
