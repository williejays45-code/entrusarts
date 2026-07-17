from alembic import op
import sqlalchemy as sa


revision = "b6f4c2d8a901"
down_revision = "9252d30e1b0a"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("evidence_id", sa.String(), nullable=False, unique=True),
        sa.Column("score_entry_id", sa.String(), nullable=False),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("evidence_type", sa.String(), nullable=False),
        sa.Column("source_name", sa.String(), nullable=False),
        sa.Column("source_value", sa.String(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("validator_status", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_evidence_score_entry",
        "evidence_records",
        ["score_entry_id"],
        unique=False,
    )
    op.create_index(
        "ix_evidence_engine_metric",
        "evidence_records",
        ["engine", "metric"],
        unique=False,
    )

    op.create_table(
        "weight_registry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("weight_id", sa.String(), nullable=False, unique=True),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("evidence_type", sa.String(), nullable=False),
        sa.Column("weight_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_weight_registry_engine_metric",
        "weight_registry",
        ["engine", "metric"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_weight_registry_engine_metric", table_name="weight_registry")
    op.drop_table("weight_registry")
    op.drop_index("ix_evidence_engine_metric", table_name="evidence_records")
    op.drop_index("ix_evidence_score_entry", table_name="evidence_records")
    op.drop_table("evidence_records")
