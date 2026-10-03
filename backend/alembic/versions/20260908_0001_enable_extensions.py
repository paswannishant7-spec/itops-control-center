"""Enable UUID and vector extensions.

Revision ID: 20260908_0001
Revises:
Create Date: 2026-09-08
"""

from alembic import op

revision: str = "20260908_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    # Extensions can be shared by other applications and may own future data.
    # Deliberately leave them installed when downgrading this revision.
    pass
