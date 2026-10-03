"""Secure device-agent enrollment, heartbeats, and retained metrics."""

import sqlalchemy as sa

from alembic import op

revision = "20260913_0013"
down_revision = "20260912_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_agents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("credential_status", sa.String(16), nullable=False),
        sa.Column("credential_hash", sa.String(64)),
        sa.Column("credential_prefix", sa.String(12)),
        sa.Column("enrollment_token_hash", sa.String(64)),
        sa.Column("enrollment_expires_at", sa.DateTime(timezone=True)),
        sa.Column("enrolled_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen", sa.DateTime(timezone=True)),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("last_metric_at", sa.DateTime(timezone=True)),
        sa.Column("missed_heartbeat_count", sa.Integer(), nullable=False),
        sa.Column("agent_version", sa.String(32)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "status IN ('ONLINE','OFFLINE','DEGRADED','UNREGISTERED','DISABLED')",
            name=op.f("ck_device_agents_status_valid"),
        ),
        sa.CheckConstraint(
            "credential_status IN ('PENDING','ACTIVE','REVOKED')",
            name=op.f("ck_device_agents_credential_status_valid"),
        ),
        sa.CheckConstraint(
            "missed_heartbeat_count >= 0",
            name=op.f("ck_device_agents_missed_heartbeat_nonnegative"),
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            ondelete="RESTRICT",
            name=op.f("fk_device_agents_asset_id_assets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_agents")),
        sa.UniqueConstraint("asset_id", name=op.f("uq_device_agents_asset_id")),
        sa.UniqueConstraint("credential_hash", name=op.f("uq_device_agents_credential_hash")),
        sa.UniqueConstraint(
            "enrollment_token_hash", name=op.f("uq_device_agents_enrollment_token_hash")
        ),
    )
    op.create_index(op.f("ix_device_agents_asset_id"), "device_agents", ["asset_id"])
    op.create_index(op.f("ix_device_agents_status"), "device_agents", ["status"])
    op.create_index(
        op.f("ix_device_agents_last_heartbeat_at"), "device_agents", ["last_heartbeat_at"]
    )

    op.create_table(
        "device_heartbeats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available", sa.Boolean(), nullable=False),
        sa.Column("resulting_status", sa.String(16), nullable=False),
        sa.Column("hostname", sa.String(255), nullable=False),
        sa.Column("operating_system", sa.String(160), nullable=False),
        sa.Column("ip_addresses", sa.JSON(), nullable=False),
        sa.Column("boot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collection_errors", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "resulting_status IN ('ONLINE','DEGRADED')",
            name=op.f("ck_device_heartbeats_resulting_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["device_agents.id"],
            ondelete="RESTRICT",
            name=op.f("fk_device_heartbeats_agent_id_device_agents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_heartbeats")),
    )
    op.create_index(op.f("ix_device_heartbeats_agent_id"), "device_heartbeats", ["agent_id"])
    op.create_index(
        "ix_device_heartbeats_agent_received", "device_heartbeats", ["agent_id", "received_at"]
    )

    op.create_table(
        "device_metrics",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("agent_id", sa.Uuid(), nullable=False),
        sa.Column("sampled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("cpu_percent", sa.Float(), nullable=False),
        sa.Column("memory_percent", sa.Float(), nullable=False),
        sa.Column("memory_used_bytes", sa.BigInteger(), nullable=False),
        sa.Column("memory_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("disk_percent", sa.Float(), nullable=False),
        sa.Column("disk_used_bytes", sa.BigInteger(), nullable=False),
        sa.Column("disk_total_bytes", sa.BigInteger(), nullable=False),
        sa.Column("network_bytes_sent", sa.BigInteger(), nullable=False),
        sa.Column("network_bytes_received", sa.BigInteger(), nullable=False),
        sa.CheckConstraint(
            "cpu_percent >= 0 AND cpu_percent <= 100 AND memory_percent >= 0 AND "
            "memory_percent <= 100 AND disk_percent >= 0 AND disk_percent <= 100",
            name=op.f("ck_device_metrics_percentages_valid"),
        ),
        sa.CheckConstraint(
            "memory_used_bytes >= 0 AND memory_total_bytes > 0 AND "
            "memory_used_bytes <= memory_total_bytes",
            name=op.f("ck_device_metrics_memory_values_valid"),
        ),
        sa.CheckConstraint(
            "disk_used_bytes >= 0 AND disk_total_bytes > 0 AND disk_used_bytes <= disk_total_bytes",
            name=op.f("ck_device_metrics_disk_values_valid"),
        ),
        sa.CheckConstraint(
            "network_bytes_sent >= 0 AND network_bytes_received >= 0",
            name=op.f("ck_device_metrics_network_values_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["agent_id"],
            ["device_agents.id"],
            ondelete="RESTRICT",
            name=op.f("fk_device_metrics_agent_id_device_agents"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_device_metrics")),
    )
    op.create_index(op.f("ix_device_metrics_agent_id"), "device_metrics", ["agent_id"])
    op.create_index("ix_device_metrics_agent_sampled", "device_metrics", ["agent_id", "sampled_at"])


def downgrade() -> None:
    op.drop_table("device_metrics")
    op.drop_table("device_heartbeats")
    op.drop_table("device_agents")
