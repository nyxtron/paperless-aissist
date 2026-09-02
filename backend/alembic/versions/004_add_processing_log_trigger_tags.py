"""Record which tags triggered a processing run.

Revision ID: 004
Revises: 003
Create Date: 2026-09-01

"""

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    insp = inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("processing_logs")}
    if "trigger_tags" not in cols:
        op.add_column(
            "processing_logs", sa.Column("trigger_tags", sa.String(), nullable=True)
        )


def downgrade():
    insp = inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("processing_logs")}
    if "trigger_tags" in cols:
        op.drop_column("processing_logs", "trigger_tags")
