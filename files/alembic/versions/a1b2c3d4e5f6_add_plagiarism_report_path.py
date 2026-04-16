"""add plagiarism_report_path to submissions

Revision ID: a1b2c3d4e5f6
Revises: 10d710702866
Create Date: 2026-04-16 06:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '10d710702866'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('submissions', sa.Column('plagiarism_report_path', sa.String(length=500), nullable=True))


def downgrade():
    op.drop_column('submissions', 'plagiarism_report_path')
