"""System roles, explicit grants, assignments and their audit trail."""

import sqlalchemy as sa

from alembic import op

revision = "20260908_0003"
down_revision = "20260908_0002"
branch_labels = None
depends_on = None

# Frozen migration snapshot; never import the live application catalog.
GRANTS = {
    "EMPLOYEE": [
        "asset:view_own",
        "knowledge:view",
        "ticket:comment",
        "ticket:create",
        "ticket:reopen",
        "ticket:view_own",
    ],
    "TECHNICIAN": [
        "ai:use",
        "alert:acknowledge",
        "alert:resolve",
        "alert:view",
        "analytics:view",
        "asset:view_own",
        "asset:view_team",
        "change:create",
        "change:update",
        "change:view",
        "incident:create",
        "incident:resolve",
        "incident:update",
        "incident:view",
        "knowledge:create",
        "knowledge:update",
        "knowledge:view",
        "monitoring:view",
        "problem:create",
        "problem:update",
        "problem:view",
        "sla:view",
        "team:view",
        "ticket:assign",
        "ticket:close",
        "ticket:comment",
        "ticket:create",
        "ticket:escalate",
        "ticket:internal_note",
        "ticket:reassign",
        "ticket:reopen",
        "ticket:resolve",
        "ticket:update",
        "ticket:view_own",
        "ticket:view_team",
    ],
    "IT_MANAGER": [
        "ai:use",
        "alert:acknowledge",
        "alert:resolve",
        "alert:view",
        "analytics:view",
        "asset:view_all",
        "asset:view_own",
        "asset:view_team",
        "change:approve",
        "change:create",
        "change:update",
        "change:view",
        "incident:create",
        "incident:resolve",
        "incident:update",
        "incident:view",
        "knowledge:archive",
        "knowledge:create",
        "knowledge:publish",
        "knowledge:review",
        "knowledge:update",
        "knowledge:view",
        "monitoring:view",
        "problem:create",
        "problem:resolve",
        "problem:update",
        "problem:view",
        "sla:view",
        "team:manage",
        "team:view",
        "ticket:assign",
        "ticket:close",
        "ticket:comment",
        "ticket:create",
        "ticket:escalate",
        "ticket:internal_note",
        "ticket:reassign",
        "ticket:reopen",
        "ticket:resolve",
        "ticket:update",
        "ticket:view_all",
        "ticket:view_own",
        "ticket:view_team",
    ],
    "ADMIN": [
        "ai:configure",
        "ai:use",
        "alert:acknowledge",
        "alert:manage",
        "alert:resolve",
        "alert:view",
        "analytics:view",
        "asset:create",
        "asset:retire",
        "asset:update",
        "asset:view_all",
        "asset:view_own",
        "asset:view_team",
        "audit:view",
        "change:approve",
        "change:create",
        "change:update",
        "change:view",
        "incident:create",
        "incident:resolve",
        "incident:update",
        "incident:view",
        "knowledge:archive",
        "knowledge:create",
        "knowledge:publish",
        "knowledge:review",
        "knowledge:update",
        "knowledge:view",
        "monitoring:manage",
        "monitoring:view",
        "permission:manage",
        "permission:view",
        "problem:create",
        "problem:resolve",
        "problem:update",
        "problem:view",
        "role:manage",
        "role:view",
        "sla:manage",
        "sla:view",
        "system:configure",
        "team:manage",
        "team:view",
        "ticket:assign",
        "ticket:close",
        "ticket:comment",
        "ticket:create",
        "ticket:escalate",
        "ticket:internal_note",
        "ticket:reassign",
        "ticket:reopen",
        "ticket:resolve",
        "ticket:update",
        "ticket:view_all",
        "ticket:view_own",
        "ticket:view_team",
        "user:create",
        "user:disable",
        "user:update",
        "user:view",
    ],
}


def upgrade() -> None:
    for name, size in (("roles", 32), ("permissions", 64)):
        op.create_table(
            name,
            sa.Column("code", sa.String(size), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    op.create_table(
        "role_permissions",
        sa.Column(
            "role_code",
            sa.String(32),
            sa.ForeignKey("roles.code", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "permission_code",
            sa.String(64),
            sa.ForeignKey("permissions.code", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index("ix_role_permissions_permission_code", "role_permissions", ["permission_code"])
    op.create_table(
        "user_roles",
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
        ),
        sa.Column(
            "role_code",
            sa.String(32),
            sa.ForeignKey("roles.code", ondelete="RESTRICT"),
            primary_key=True,
        ),
    )
    op.create_index("ix_user_roles_role_code", "user_roles", ["role_code"])
    op.create_table(
        "role_assignment_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "actor_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("before_roles", sa.JSON(), nullable=False),
        sa.Column("after_roles", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_role_assignment_events_user_id", "role_assignment_events", ["user_id"])
    op.bulk_insert(sa.table("roles", sa.column("code", sa.String())), [{"code": r} for r in GRANTS])
    op.bulk_insert(
        sa.table("permissions", sa.column("code", sa.String())),
        [{"code": p} for p in sorted({p for values in GRANTS.values() for p in values})],
    )
    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role_code", sa.String()),
            sa.column("permission_code", sa.String()),
        ),
        [{"role_code": r, "permission_code": p} for r, values in GRANTS.items() for p in values],
    )


def downgrade() -> None:
    # Only use on a disposable DB: this removes grants and their history.
    for table in (
        "role_assignment_events",
        "user_roles",
        "role_permissions",
        "permissions",
        "roles",
    ):
        op.drop_table(table)
