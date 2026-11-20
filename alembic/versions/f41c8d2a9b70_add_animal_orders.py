"""Add animal orders with ID and data variants in a shared table.

Revision ID: f41c8d2a9b70
Revises: d6f7a21b903e
"""
from alembic import op
import sqlalchemy as sa


revision = "f41c8d2a9b70"
down_revision = "d6f7a21b903e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "animal_orders",
        sa.Column("uuid", sa.String(), nullable=False),
        sa.Column("order_type", sa.String(), nullable=False),
        sa.Column("licence", sa.String(), nullable=False),
        sa.Column("line", sa.String(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("user", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("ids", sa.JSON(none_as_null=True), nullable=True),
        sa.Column("sex", sa.String(), nullable=True),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("uuid"),
        sa.CheckConstraint(
            "order_type IN ('by_id', 'by_data')", name="ck_animal_orders_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="ck_animal_orders_status",
        ),
        sa.CheckConstraint(
            "(order_type = 'by_id' AND ids IS NOT NULL AND sex IS NULL "
            "AND age IS NULL AND amount IS NULL) OR "
            "(order_type = 'by_data' AND ids IS NULL AND sex IS NOT NULL "
            "AND age IS NOT NULL AND amount IS NOT NULL)",
            name="ck_animal_orders_selection",
        ),
        sa.CheckConstraint(
            "ids IS NULL OR (json_valid(ids) AND json_type(ids) = 'array' "
            "AND json_array_length(ids) > 0)", name="ck_animal_orders_ids",
        ),
        sa.CheckConstraint(
            "sex IS NULL OR sex IN ('female', 'male', 'unknown')",
            name="ck_animal_orders_sex",
        ),
        sa.CheckConstraint(
            "age IS NULL OR (typeof(age) = 'integer' AND age >= 0)",
            name="ck_animal_orders_age",
        ),
        sa.CheckConstraint(
            "amount IS NULL OR (typeof(amount) = 'integer' AND amount > 0)",
            name="ck_animal_orders_amount",
        ),
    )
    op.create_index("ix_animal_orders_user", "animal_orders", ["user"])
    op.create_index("ix_animal_orders_status", "animal_orders", ["status"])


def downgrade() -> None:
    op.drop_table("animal_orders")
