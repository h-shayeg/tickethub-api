"""restrict user roles

Revision ID: abe49a05295f
Revises: ae1fa574b1c3
Create Date: 2026-11-04 07:22:37.730063

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'abe49a05295f'
down_revision: Union[str, None] = 'ae1fa574b1c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Written by hand: autogenerate does not detect CHECK constraints.
# The upgrade fails if a row already has another role. That is on purpose:
# fix the row first instead of silently changing someone's permissions.


def upgrade() -> None:
    op.create_check_constraint(
        op.f("ck_users_role_valid"), "users", "role IN ('user', 'admin')"
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_role_valid"), "users", type_="check")
