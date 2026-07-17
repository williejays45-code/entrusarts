from alembic import op
import sqlalchemy as sa


revision = "9252d30e1b0a"
down_revision = "629a1ec59107"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "decision_trace",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("score_entry_id", sa.String(), nullable=False),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("metric", sa.String(), nullable=False),
        sa.Column("score_value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("decision_context", sa.String(), nullable=False),
        sa.Column("decision_impact", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("recovery_action", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index(
        "ix_score_entries_engine_score",
        "score_entries",
        ["engine", "score_name"],
        unique=False,
    )
    op.create_index(
        "ix_score_history_entry_time",
        "score_history",
        ["score_entry_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_decision_trace_score_entry",
        "decision_trace",
        ["score_entry_id"],
        unique=False,
    )
    op.create_index(
        "ix_decision_trace_engine_metric",
        "decision_trace",
        ["engine", "metric"],
        unique=False,
    )
    op.create_index(
        "ix_deal_observations_constant",
        "deal_observations",
        ["constant_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_graduation_records_constant",
        "graduation_records",
        ["constant_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_graduation_records_constant", table_name="graduation_records")
    op.drop_index("ix_deal_observations_constant", table_name="deal_observations")
    op.drop_index("ix_decision_trace_engine_metric", table_name="decision_trace")
    op.drop_index("ix_decision_trace_score_entry", table_name="decision_trace")
    op.drop_table("decision_trace")
    op.drop_index("ix_score_history_entry_time", table_name="score_history")
    op.drop_index("ix_score_entries_engine_score", table_name="score_entries")
