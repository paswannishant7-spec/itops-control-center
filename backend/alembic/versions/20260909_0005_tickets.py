"""Ticket intake, collaboration, assignment, attachments and lifecycle."""

import sqlalchemy as sa

from alembic import op

revision = "20260909_0005"
down_revision = "20260909_0004"
branch_labels = None
depends_on = None


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
        "ticket_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_categories")),
    )
    op.create_index(
        "uq_ticket_categories_code_normalized",
        "ticket_categories",
        [sa.literal_column("lower(code)")],
        unique=True,
    )
    op.create_index(
        "uq_ticket_categories_name_normalized",
        "ticket_categories",
        [sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "ticket_subcategories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["ticket_categories.id"],
            name=op.f("fk_ticket_subcategories_category_id_ticket_categories"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_subcategories")),
    )
    op.create_index(
        op.f("ix_ticket_subcategories_category_id"), "ticket_subcategories", ["category_id"]
    )
    op.create_index(
        "uq_ticket_subcategories_category_code",
        "ticket_subcategories",
        ["category_id", sa.literal_column("lower(code)")],
        unique=True,
    )
    op.create_index(
        "uq_ticket_subcategories_category_name",
        "ticket_subcategories",
        ["category_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    op.create_table(
        "tickets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reference", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column("department_id", sa.Uuid()),
        sa.Column("location_id", sa.Uuid()),
        sa.Column("asset_id", sa.Uuid()),
        sa.Column("category_id", sa.Uuid()),
        sa.Column("subcategory_id", sa.Uuid()),
        sa.Column("impact", sa.String(16), nullable=False),
        sa.Column("urgency", sa.String(16), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("assignment_team_id", sa.Uuid()),
        sa.Column("assigned_technician_id", sa.Uuid()),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("first_response_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("reopened_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_summary", sa.Text()),
        sa.Column("resolution_code", sa.String(64)),
        *timestamps(),
        sa.CheckConstraint(
            "impact IN ('LOW', 'MEDIUM', 'HIGH')", name=op.f("ck_tickets_impact_valid")
        ),
        sa.CheckConstraint(
            "urgency IN ('LOW', 'MEDIUM', 'HIGH')", name=op.f("ck_tickets_urgency_valid")
        ),
        sa.CheckConstraint(
            "priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name=op.f("ck_tickets_priority_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('NEW', 'OPEN', 'IN_PROGRESS', 'PENDING_USER', 'PENDING_VENDOR', "
            "'ESCALATED', 'RESOLVED', 'CLOSED', 'CANCELLED')",
            name=op.f("ck_tickets_status_valid"),
        ),
        sa.CheckConstraint("source IN ('PORTAL', 'API')", name=op.f("ck_tickets_source_valid")),
        sa.CheckConstraint(
            "assigned_technician_id IS NULL OR assignment_team_id IS NOT NULL",
            name=op.f("ck_tickets_technician_requires_team"),
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            name=op.f("fk_tickets_requester_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["departments.id"],
            name=op.f("fk_tickets_department_id_departments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["location_id"],
            ["locations.id"],
            name=op.f("fk_tickets_location_id_locations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["category_id"],
            ["ticket_categories.id"],
            name=op.f("fk_tickets_category_id_ticket_categories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["subcategory_id"],
            ["ticket_subcategories.id"],
            name=op.f("fk_tickets_subcategory_id_ticket_subcategories"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assignment_team_id"],
            ["teams.id"],
            name=op.f("fk_tickets_assignment_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_technician_id"],
            ["users.id"],
            name=op.f("fk_tickets_assigned_technician_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        sa.UniqueConstraint("reference", name=op.f("uq_tickets_reference")),
    )
    for column in (
        "requester_id",
        "department_id",
        "location_id",
        "asset_id",
        "category_id",
        "subcategory_id",
        "priority",
        "status",
        "assignment_team_id",
        "assigned_technician_id",
    ):
        op.create_index(op.f(f"ix_tickets_{column}"), "tickets", [column])
    op.create_index("ix_tickets_status_created_at", "tickets", ["status", "created_at"])
    op.create_index("ix_tickets_team_status", "tickets", ["assignment_team_id", "status"])

    op.create_table(
        "ticket_comments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("visibility", sa.String(16), nullable=False),
        *timestamps(),
        sa.CheckConstraint(
            "visibility IN ('PUBLIC', 'INTERNAL')", name=op.f("ck_ticket_comments_visibility_valid")
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_comments_ticket_id_tickets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["users.id"],
            name=op.f("fk_ticket_comments_author_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_comments")),
    )
    op.create_index(op.f("ix_ticket_comments_ticket_id"), "ticket_comments", ["ticket_id"])
    op.create_index(op.f("ix_ticket_comments_author_id"), "ticket_comments", ["author_id"])
    op.create_index(
        "ix_ticket_comments_ticket_created", "ticket_comments", ["ticket_id", "created_at"]
    )

    op.create_table(
        "ticket_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("uploader_id", sa.Uuid(), nullable=False),
        sa.Column("original_name", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("size_bytes > 0", name=op.f("ck_ticket_attachments_size_positive")),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_attachments_ticket_id_tickets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["uploader_id"],
            ["users.id"],
            name=op.f("fk_ticket_attachments_uploader_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_attachments")),
        sa.UniqueConstraint("storage_key", name=op.f("uq_ticket_attachments_storage_key")),
    )
    op.create_index(op.f("ix_ticket_attachments_ticket_id"), "ticket_attachments", ["ticket_id"])
    op.create_index(
        op.f("ix_ticket_attachments_uploader_id"), "ticket_attachments", ["uploader_id"]
    )
    op.create_index(
        "ix_ticket_attachments_ticket_created", "ticket_attachments", ["ticket_id", "created_at"]
    )

    op.create_table(
        "ticket_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("before_state", sa.JSON()),
        sa.Column("after_state", sa.JSON()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_events_ticket_id_tickets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["users.id"],
            name=op.f("fk_ticket_events_actor_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_events")),
    )
    op.create_index(op.f("ix_ticket_events_ticket_id"), "ticket_events", ["ticket_id"])
    op.create_index(op.f("ix_ticket_events_actor_id"), "ticket_events", ["actor_id"])
    op.create_index("ix_ticket_events_ticket_created", "ticket_events", ["ticket_id", "created_at"])

    op.create_table(
        "ticket_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("team_id", sa.Uuid(), nullable=False),
        sa.Column("technician_id", sa.Uuid()),
        sa.Column("assigned_by_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_ticket_assignments_interval_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_assignments_ticket_id_tickets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["team_id"],
            ["teams.id"],
            name=op.f("fk_ticket_assignments_team_id_teams"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["technician_id"],
            ["users.id"],
            name=op.f("fk_ticket_assignments_technician_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"],
            ["users.id"],
            name=op.f("fk_ticket_assignments_assigned_by_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ticket_assignments")),
    )
    op.create_index(op.f("ix_ticket_assignments_ticket_id"), "ticket_assignments", ["ticket_id"])
    op.create_index(op.f("ix_ticket_assignments_team_id"), "ticket_assignments", ["team_id"])
    op.create_index(
        op.f("ix_ticket_assignments_technician_id"), "ticket_assignments", ["technician_id"]
    )
    op.create_index(
        "uq_ticket_assignments_active",
        "ticket_assignments",
        ["ticket_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("ticket_assignments")
    op.drop_table("ticket_events")
    op.drop_table("ticket_attachments")
    op.drop_table("ticket_comments")
    op.drop_table("tickets")
    op.drop_table("ticket_subcategories")
    op.drop_table("ticket_categories")
