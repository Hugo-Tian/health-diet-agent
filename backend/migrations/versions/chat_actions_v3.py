"""Chat history and atomic multi-day proposal batches."""
from alembic import op
import sqlalchemy as sa
revision='chat_actions_v3'
down_revision='food_provenance_v2'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('adjustment_proposals',sa.Column('batch_id',sa.String(36),nullable=True))
    op.create_index('ix_adjustment_proposals_batch_id','adjustment_proposals',['batch_id'])
    op.create_table('chat_turns',sa.Column('id',sa.Integer(),primary_key=True),sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id',ondelete='CASCADE'),nullable=False),sa.Column('local_date',sa.Date(),nullable=False),sa.Column('question',sa.String(2000),nullable=False),sa.Column('answer',sa.JSON(),nullable=False),sa.Column('request_id',sa.String(36),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True)),sa.UniqueConstraint('user_id','request_id'))
    op.create_index('ix_chat_turns_user_id','chat_turns',['user_id'])

def downgrade():
    op.drop_table('chat_turns')
    with op.batch_alter_table('adjustment_proposals') as batch:
        batch.drop_index('ix_adjustment_proposals_batch_id')
        batch.drop_column('batch_id')
