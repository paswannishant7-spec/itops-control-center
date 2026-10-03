"""Create identity and refresh session tables.

Revision ID: 20260908_0002
Revises: 20260908_0001
Create Date: 2026-09-08
"""

import sqlalchemy as sa

from alembic import op

revision: str = "20260908_0002"
down_revision: str | None = "20260908_0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED', 'LOCKED')", name=op.f("ck_users_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        "uq_users_email_normalized", "users", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "refresh_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("family_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["replaced_by_id"],
            ["refresh_sessions.id"],
            name=op.f("fk_refresh_sessions_replaced_by_id_refresh_sessions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_sessions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_sessions")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_refresh_sessions_token_hash")),
    )
    op.create_index(op.f("ix_refresh_sessions_user_id"), "refresh_sessions", ["user_id"])
    op.create_index(op.f("ix_refresh_sessions_family_id"), "refresh_sessions", ["family_id"])
    op.create_index(op.f("ix_refresh_sessions_expires_at"), "refresh_sessions", ["expires_at"])
    op.create_index(
        "ix_refresh_sessions_family_active", "refresh_sessions", ["family_id", "revoked_at"]
    )
    op.create_table(
        "password_reset_tokens",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_password_reset_tokens_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_tokens")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_tokens_token_hash")),
    )
    op.create_index(op.f("ix_password_reset_tokens_user_id"), "password_reset_tokens", ["user_id"])
    op.create_index(
        op.f("ix_password_reset_tokens_expires_at"), "password_reset_tokens", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_table("password_reset_tokens")
    op.drop_table("refresh_sessions")
    op.drop_table("users")
