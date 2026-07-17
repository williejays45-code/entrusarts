from alembic import op
import sqlalchemy as sa


revision = "58b8e3f400cd"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "score_entries",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("score_name", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("validator_status", sa.String(), nullable=False),
        sa.Column("weight_table", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "sev_audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entry_id", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "tracked_constants",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("constant_name", sa.String(), nullable=False),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("frequency_class", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("notes", sa.String(), nullable=True),
    )

    op.create_table(
        "graduation_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("constant_id", sa.String(), sa.ForeignKey("tracked_constants.id")),
        sa.Column("record_type", sa.String(), nullable=False),
        sa.Column("signature", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )

    op.create_table(
        "deal_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("constant_id", sa.String(), sa.ForeignKey("tracked_constants.id")),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("actual_value", sa.Float(), nullable=False),
        sa.Column("variance", sa.Float(), nullable=False),
        sa.Column("observed_at", sa.Date(), nullable=False),
    )


def downgrade():
    op.drop_table("deal_observations")
    op.drop_table("graduation_records")
    op.drop_table("tracked_constants")
    op.drop_table("sev_audit_log")
    op.drop_table("score_entries")