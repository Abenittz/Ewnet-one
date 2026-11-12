"""add book slug

Revision ID: b8e4c2a91f01
Revises: a6510d4bb786
Create Date: 2026-11-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8e4c2a91f01"
down_revision: Union[str, None] = "a6510d4bb786"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("books", sa.Column("slug", sa.String(length=128), nullable=True))
    op.create_index("ix_books_slug", "books", ["slug"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_books_slug", table_name="books")
    op.drop_column("books", "slug")
