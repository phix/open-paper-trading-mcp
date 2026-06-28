"""Add client_intent_id to orders table (ADR 0003 idempotency)

Revision ID: 004
Revises: 85471114549d
Create Date: 2026-06-28 00:00:00.000000

Adds a nullable, indexed ``client_intent_id`` to ``orders`` so the Hub can honor
a stable client-supplied idempotency key: a repeated key returns the existing
order instead of creating a duplicate paper trade. Nullable so normal REST/MCP
orders are unaffected.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: str | Sequence[str] | None = "85471114549d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the nullable, indexed client_intent_id column to orders."""
    op.add_column(
        "orders",
        sa.Column("client_intent_id", sa.String(), nullable=True),
    )
    op.create_index("ix_orders_client_intent_id", "orders", ["client_intent_id"])


def downgrade() -> None:
    """Drop the client_intent_id column and its index."""
    op.drop_index("ix_orders_client_intent_id", table_name="orders")
    op.drop_column("orders", "client_intent_id")
