"""create models table

Revision ID: 20260507_0001
Revises:
Create Date: 2026-05-07
"""

from alembic import op
import sqlalchemy as sa


revision = "20260507_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "models",
        sa.Column("model_id", sa.String(length=128), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("quantization", sa.String(length=32), nullable=False, server_default="unknown"),
        sa.Column("size_gb", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pulled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="downloading"),
        sa.Column("benchmark_score", sa.Float(), nullable=True),
        sa.Column("tokens_per_sec", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("models")
