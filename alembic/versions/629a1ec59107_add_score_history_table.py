from alembic import op
import sqlalchemy as sa
revision = "629a1ec59107"
down_revision = "58b8e3f400cd"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table(
        "score_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("score_entry_id", sa.String(), nullable=False),
        sa.Column("engine", sa.String(), nullable=False),
        sa.Column("score_name", sa.String(), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.String(), nullable=False),
        sa.Column("validator_status", sa.String(), nullable=False),
        sa.Column("weight_table", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
def downgrade():
    op.drop_table("score_history")
