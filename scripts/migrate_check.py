import subprocess
import sys

subprocess.check_call(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-q",
        "sqlalchemy==2.0.36",
        "alembic==1.14.0",
        "psycopg2-binary",
        "pydantic",
        "pydantic-settings",
        "email-validator",
        "greenlet",
    ]
)
subprocess.check_call([sys.executable, "-m", "alembic", "upgrade", "head"])

from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg2://docchat:docchat@postgres:5432/docchat")
with engine.connect() as conn:
    tables = conn.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")
    ).fetchall()
    print("tables", [t[0] for t in tables])
