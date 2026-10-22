"""Track authoritative sources while retaining retired demo foods for old logs."""
from alembic import op
import sqlalchemy as sa
revision='food_provenance_v2'
down_revision='2f692f8eba1e'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('foods',sa.Column('active',sa.Boolean(),nullable=False,server_default=sa.true()))
    op.add_column('foods',sa.Column('provenance',sa.JSON(),nullable=False,server_default='{}'))

def downgrade():
    with op.batch_alter_table('foods') as batch:
        batch.drop_column('provenance')
        batch.drop_column('active')
