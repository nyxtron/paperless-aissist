"""Add indexes on processing_logs.document_id, status, processed_at.

Revision ID: 002
Revises: 001
Create Date: 2026-04-21

"""

from alembic import op

revision = "002"
down_revision = "6108ef3356a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_log_document_id", "processing_logs", ["document_id"])
    op.create_index("ix_log_status", "processing_logs", ["status"])
    op.create_index("ix_log_processed_at", "processing_logs", ["processed_at"])


def downgrade():
    op.drop_index("ix_log_document_id", table_name="processing_logs")
    op.drop_index("ix_log_status", table_name="processing_logs")
    op.drop_index("ix_log_processed_at", table_name="processing_logs")
