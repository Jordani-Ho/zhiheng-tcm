"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# 【Epic 1 纪律】手写 revision：禁用 --autogenerate；upgrade/downgrade 都要可重跑；
# 评论头必须写明：对齐白皮文章节、回退方案、涉及存量表清单（见 docs/epic1-template-design-v1.md §6.7）。
revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade():
    ${upgrades if upgrades else "pass"}


def downgrade():
    ${downgrades if downgrades else "pass"}
