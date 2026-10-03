"""Users, departments, locations, teams, technician membership and directory audit."""

import sqlalchemy as sa

from alembic import op

revision = "20260909_0004"
down_revision = "20260908_0003"
branch_labels = None
depends_on = None

NEW_GRANTS = {
    "TECHNICIAN": ["department:view", "location:view"],
    "IT_MANAGER": ["department:view", "location:view"],
    "ADMIN": [
        "department:view",
        "department:manage",
        "location:view",
        "location:manage",
    ],
}


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("status", sa.String(16), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')", name=op.f("ck_departments_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_departments")),
    )
    op.create_index(
        "uq_departments_code_normalized",
        "departments",
        [sa.literal_column("lower(code)")],
        unique=True,
    )
    op.create_index(
        "uq_departments_name_normalized",
        "departments",
        [sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("address", sa.String(500)),
        sa.Column("status", sa.String(16), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INACTIVE')", name=op.f("ck_locations_status_valid")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locations")),
    )
    op.create_index(
        "uq_locations_code_normalized",
        "locations",
        [sa.literal_column("lower(code)")],
        unique=True,
    )
    op.create_index(
        "uq_locations_name_normalized",
        "locations",
        [sa.literal_column("lower(name)")],
        unique=True,
    )

    op.add_column("users", sa.Column("employee_number", sa.String(64)))
    op.add_column("users", sa.Column("job_title", sa.String(120)))
    op.add_column("users", sa.Column("department_id", sa.Uuid()))
    op.add_column("users", sa.Column("location_id", sa.Uuid()))
    op.create_foreign_key(
        op.f("fk_users_department_id_departments"),
        "users",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_users_location_id_locations"),
        "users",
        "locations",
        ["location_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_users_department_id"), "users", ["department_id"])
    op.create_index(op.f("ix_users_location_id"), "users", ["location_id"])
    op.create_index(
        "uq_users_employee_number_normalized",
        "users",
        [sa.literal_column("lower(employee_number)")],
        unique=True,
    )

    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("department_id", sa.Uuid()),
        sa.Column("location_id", sa.Uuid()),
        *timestamps(),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name=op.f("ck_teams_status_valid")),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_teams_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_teams_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teams")),
    )
    op.create_index(op.f("ix_teams_department_id"), "teams", ["department_id"])
    op.create_index(op.f("ix_teams_location_id"), "teams", ["location_id"])
    op.create_index(
        "uq_teams_code_normalized", "teams", [sa.literal_column("lower(code)")], unique=True
    )
    op.create_index(
        "uq_teams_name_normalized", "teams", [sa.literal_column("lower(name)")], unique=True
    )
    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("member_role", sa.String(16), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "member_role IN ('MEMBER', 'LEAD')", name=op.f("ck_team_members_member_role_valid")
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_team_members_interval_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_team_members_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_team_members_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_members")),
    )
    op.create_index(op.f("ix_team_members_team_id"), "team_members", ["team_id"])
    op.create_index(op.f("ix_team_members_user_id"), "team_members", ["user_id"])
    op.create_index(
        "uq_team_members_active",
        "team_members",
        ["team_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )
    op.create_table(
        "directory_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_directory_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_directory_events")),
    )
    op.create_index(op.f("ix_directory_events_actor_id"), "directory_events", ["actor_id"])
    op.create_index(op.f("ix_directory_events_created_at"), "directory_events", ["created_at"])
    op.create_index(
        "ix_directory_events_entity",
        "directory_events",
        ["entity_type", "entity_id", "created_at"],
    )

    permissions = sorted({permission for values in NEW_GRANTS.values() for permission in values})
    op.bulk_insert(
        sa.table("permissions", sa.column("code", sa.String())),
        [{"code": permission} for permission in permissions],
    )
    op.bulk_insert(
        sa.table(
            "role_permissions",
            sa.column("role_code", sa.String()),
            sa.column("permission_code", sa.String()),
        ),
        [
            {"role_code": role, "permission_code": permission}
            for role, permissions_for_role in NEW_GRANTS.items()
            for permission in permissions_for_role
        ],
    )


def downgrade() -> None:
    permissions = sorted({permission for values in NEW_GRANTS.values() for permission in values})
    role_permissions = sa.table(
        "role_permissions",
        sa.column("role_code", sa.String()),
        sa.column("permission_code", sa.String()),
    )
    permission_table = sa.table("permissions", sa.column("code", sa.String()))
    op.execute(role_permissions.delete().where(role_permissions.c.permission_code.in_(permissions)))
    op.execute(permission_table.delete().where(permission_table.c.code.in_(permissions)))
    op.drop_table("directory_events")
    op.drop_table("team_members")
    op.drop_table("teams")
    op.drop_index("uq_users_employee_number_normalized", table_name="users")
    op.drop_index(op.f("ix_users_location_id"), table_name="users")
    op.drop_index(op.f("ix_users_department_id"), table_name="users")
    op.drop_constraint(op.f("fk_users_location_id_locations"), "users", type_="foreignkey")
    op.drop_constraint(op.f("fk_users_department_id_departments"), "users", type_="foreignkey")
    op.drop_column("users", "location_id")
    op.drop_column("users", "department_id")
    op.drop_column("users", "job_title")
    op.drop_column("users", "employee_number")
    op.drop_table("locations")
    op.drop_table("departments")
