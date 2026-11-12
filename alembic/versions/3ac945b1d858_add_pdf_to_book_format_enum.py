"""add_pdf_to_book_format_enum

Revision ID: 3ac945b1d858
Revises: 0e161d13df33
Create Date: 2026-10-09 20:48:58.191666

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ac945b1d858'
down_revision: Union[str, None] = '0e161d13df33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE book_format ADD VALUE IF NOT EXISTS 'PDF'")


def downgrade() -> None:
    pass
