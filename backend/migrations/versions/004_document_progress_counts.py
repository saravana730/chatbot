"""Add progress_current / progress_total / progress_percent for ingest UX.

Revision ID: 004
Revises: 003
Create Date: 2026-11-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("progress_current", sa.Integer(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("progress_total", sa.Integer(), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("progress_percent", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("documents", "progress_percent")
    op.drop_column("documents", "progress_total")
    op.drop_column("documents", "progress_current")
