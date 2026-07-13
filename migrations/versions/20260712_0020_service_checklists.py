"""Adiciona checklists, aceite e retorno em garantia.

Revision ID: 20260712_0020
Revises: 20260712_0019
"""
import sqlalchemy as sa
from alembic import op

revision = "20260712_0020"
down_revision = "20260712_0019"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "service_checklist_templates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], name="fk_checklist_template_org"),
        sa.UniqueConstraint("organization_id", "category", "version", name="uq_checklist_org_category_version"),
    )
    op.create_index("ix_service_checklist_templates_organization_id", "service_checklist_templates", ["organization_id"])
    op.create_index("ix_service_checklist_templates_category", "service_checklist_templates", ["category"])
    with op.batch_alter_table("ordens_servico") as batch:
        batch.add_column(sa.Column("checklist_template_id", sa.Integer()))
        batch.add_column(sa.Column("checklist_snapshot", sa.JSON()))
        batch.add_column(sa.Column("checklist_answers", sa.JSON()))
        batch.add_column(sa.Column("authorization_accepted_at", sa.DateTime()))
        batch.add_column(sa.Column("authorization_accepted_by", sa.String(length=120)))
        batch.add_column(sa.Column("warranty_return_of_id", sa.Integer()))
        batch.create_foreign_key("fk_order_checklist_template", "service_checklist_templates", ["checklist_template_id"], ["id"])
        batch.create_foreign_key("fk_order_warranty_origin", "ordens_servico", ["warranty_return_of_id"], ["id"])
        batch.create_index("ix_ordens_servico_warranty_return_of_id", ["warranty_return_of_id"])


def downgrade():
    with op.batch_alter_table("ordens_servico") as batch:
        batch.drop_index("ix_ordens_servico_warranty_return_of_id")
        batch.drop_constraint("fk_order_warranty_origin", type_="foreignkey")
        batch.drop_constraint("fk_order_checklist_template", type_="foreignkey")
        for column in (
            "warranty_return_of_id", "authorization_accepted_by", "authorization_accepted_at",
            "checklist_answers", "checklist_snapshot", "checklist_template_id",
        ):
            batch.drop_column(column)
    op.drop_table("service_checklist_templates")
