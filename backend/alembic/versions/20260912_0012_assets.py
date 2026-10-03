"""Asset inventory, assignment history, ownership, and ticket relationships."""

import sqlalchemy as sa

from alembic import op

revision = "20260912_0012"
down_revision = "20260911_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_tag", sa.String(64), nullable=False),
        sa.Column("serial_number", sa.String(128)),
        sa.Column("hostname", sa.String(255)),
        sa.Column("asset_type", sa.String(32), nullable=False),
        sa.Column("manufacturer", sa.String(120)),
        sa.Column("model", sa.String(120)),
        sa.Column("operating_system", sa.String(160)),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("mac_address", sa.String(17)),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("department_id", sa.Uuid()),
        sa.Column("location_id", sa.Uuid()),
        sa.Column("purchase_date", sa.Date()),
        sa.Column("warranty_end", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("health_status", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "asset_type IN ('LAPTOP','DESKTOP','MONITOR','PRINTER','SERVER',"
            "'NETWORK_DEVICE','MOBILE_DEVICE')",
            name=op.f("ck_assets_asset_type_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE','IN_REPAIR','LOST','RETIRED','DISPOSED')",
            name=op.f("ck_assets_status_valid"),
        ),
        sa.CheckConstraint(
            "health_status IN ('UNKNOWN','HEALTHY','WARNING','CRITICAL','OFFLINE')",
            name=op.f("ck_assets_health_status_valid"),
        ),
        sa.CheckConstraint(
            "warranty_end IS NULL OR purchase_date IS NULL OR warranty_end >= purchase_date",
            name=op.f("ck_assets_warranty_interval_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["users.id"], ondelete="RESTRICT", name=op.f("fk_assets_owner_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            ondelete="RESTRICT",
            name=op.f("fk_assets_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            ondelete="RESTRICT",
            name=op.f("fk_assets_location_id_locations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
    )
    op.create_index(
        "uq_assets_tag_normalized", "assets", [sa.text("lower(asset_tag)")], unique=True
    )
    op.create_index(
        "uq_assets_serial_normalized", "assets", [sa.text("lower(serial_number)")], unique=True
    )
    for column in ("asset_type", "owner_id", "department_id", "location_id"):
        op.create_index(op.f(f"ix_assets_{column}"), "assets", [column])
    op.create_index("ix_assets_status_health", "assets", ["status", "health_status"])

    op.create_table(
        "asset_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid()),
        sa.Column("department_id", sa.Uuid()),
        sa.Column("location_id", sa.Uuid()),
        sa.Column("assigned_by_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "owner_id IS NOT NULL OR department_id IS NOT NULL OR location_id IS NOT NULL",
            name=op.f("ck_asset_assignments_target_required"),
        ),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_asset_assignments_interval_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_asset_assignments_asset_id_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_asset_assignments_owner_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            ondelete="RESTRICT",
            name=op.f("fk_asset_assignments_department_id_departments"),
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            ondelete="RESTRICT",
            name=op.f("fk_asset_assignments_location_id_locations"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_asset_assignments_assigned_by_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_assignments")),
    )
    for column in ("asset_id", "owner_id", "department_id", "location_id"):
        op.create_index(op.f(f"ix_asset_assignments_{column}"), "asset_assignments", [column])
    op.create_index(
        "uq_asset_assignments_active",
        "asset_assignments",
        ["asset_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )
    op.create_index(
        "ix_asset_assignments_asset_started", "asset_assignments", ["asset_id", "started_at"]
    )

    op.create_table(
        "asset_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_asset_events_asset_id_assets"),
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name=op.f("fk_asset_events_actor_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_events")),
    )
    op.create_index(op.f("ix_asset_events_asset_id"), "asset_events", ["asset_id"])
    op.create_index(op.f("ix_asset_events_actor_id"), "asset_events", ["actor_id"])
    op.create_index("ix_asset_events_asset_created", "asset_events", ["asset_id", "created_at"])
    op.create_foreign_key(
        op.f("fk_tickets_asset_id_assets"),
        "tickets",
        "assets",
        ["asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_tickets_asset_id_assets"), "tickets", type_="foreignkey")
    op.drop_table("asset_events")
    op.drop_table("asset_assignments")
    op.drop_table("assets")
