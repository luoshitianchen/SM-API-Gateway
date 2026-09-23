"""新增业务表（API 密钥 / 路由 / 限流规则 / 上游健康）

Revision ID: 0002_business_tables
Revises: 0001_initial
Create Date: 2026-09-23
"""
from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# 本迁移由 autogenerate 生成，手动调整 revision 标识为 0002_business_tables
revision: str = '0002_business_tables'
down_revision: Union[str, None] = '0001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### 自动生成开始：创建网关业务表 ###
    # API 密钥表：管理调用方密钥及状态
    op.create_table('gateway_api_keys',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('key_id', sa.String(length=64), nullable=False),
    sa.Column('key_hash', sa.String(length=256), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('owner', sa.String(length=128), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gateway_api_keys_key_id'), 'gateway_api_keys', ['key_id'], unique=True)
    op.create_index(op.f('ix_gateway_api_keys_status'), 'gateway_api_keys', ['status'], unique=False)
    # 限流规则表：按 key 类型配置 RPM 与突发流量
    op.create_table('gateway_rate_limit_rules',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('key_type', sa.String(length=16), nullable=False),
    sa.Column('limit_rpm', sa.Integer(), nullable=False),
    sa.Column('burst', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gateway_rate_limit_rules_key_type'), 'gateway_rate_limit_rules', ['key_type'], unique=False)
    op.create_index(op.f('ix_gateway_rate_limit_rules_name'), 'gateway_rate_limit_rules', ['name'], unique=True)
    op.create_index(op.f('ix_gateway_rate_limit_rules_status'), 'gateway_rate_limit_rules', ['status'], unique=False)
    # 路由表：路径模式到上游服务的映射
    op.create_table('gateway_routes',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('path_pattern', sa.String(length=256), nullable=False),
    sa.Column('upstream_url', sa.String(length=512), nullable=False),
    sa.Column('methods', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gateway_routes_path_pattern'), 'gateway_routes', ['path_pattern'], unique=True)
    op.create_index(op.f('ix_gateway_routes_status'), 'gateway_routes', ['status'], unique=False)
    # 上游健康表：记录上游服务健康检查结果
    op.create_table('gateway_upstream_health',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('upstream_name', sa.String(length=128), nullable=False),
    sa.Column('upstream_url', sa.String(length=512), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('last_check_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error', sa.Text(), nullable=False),
    sa.Column('consecutive_failures', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_gateway_upstream_health_status'), 'gateway_upstream_health', ['status'], unique=False)
    op.create_index(op.f('ix_gateway_upstream_health_upstream_name'), 'gateway_upstream_health', ['upstream_name'], unique=True)
    # ### 自动生成结束 ###


def downgrade() -> None:
    # ### 自动生成开始：回滚业务表 ###
    op.drop_index(op.f('ix_gateway_upstream_health_upstream_name'), table_name='gateway_upstream_health')
    op.drop_index(op.f('ix_gateway_upstream_health_status'), table_name='gateway_upstream_health')
    op.drop_table('gateway_upstream_health')
    op.drop_index(op.f('ix_gateway_routes_status'), table_name='gateway_routes')
    op.drop_index(op.f('ix_gateway_routes_path_pattern'), table_name='gateway_routes')
    op.drop_table('gateway_routes')
    op.drop_index(op.f('ix_gateway_rate_limit_rules_status'), table_name='gateway_rate_limit_rules')
    op.drop_index(op.f('ix_gateway_rate_limit_rules_name'), table_name='gateway_rate_limit_rules')
    op.drop_index(op.f('ix_gateway_rate_limit_rules_key_type'), table_name='gateway_rate_limit_rules')
    op.drop_table('gateway_rate_limit_rules')
    op.drop_index(op.f('ix_gateway_api_keys_status'), table_name='gateway_api_keys')
    op.drop_index(op.f('ix_gateway_api_keys_key_id'), table_name='gateway_api_keys')
    op.drop_table('gateway_api_keys')
    # ### 自动生成结束 ###
