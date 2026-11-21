from sqlalchemy import (JSON, Column, ForeignKey, Index, Integer, MetaData,
                        String, Table, Text, UniqueConstraint)

schema = MetaData()
users = Table('accounts', schema,
    Column('id', Integer, primary_key=True),
    Column('username', String(40), nullable=False, unique=True),
    Column('password_hash', String(200), nullable=False),
    Column('role', String(20), nullable=False))
cases = Table('business_cases', schema,
    Column('id', Integer, primary_key=True),
    Column('slug', String(64), nullable=False, unique=True),
    Column('title', String(120), nullable=False),
    Column('payload', JSON, nullable=False),
    Column('author', String(40), nullable=False),
    Column('created_at', String(32), nullable=False))
runs = Table('business_runs', schema,
    Column('id', Integer, primary_key=True),
    Column('case_id', ForeignKey('business_cases.id'), nullable=False, index=True),
    Column('status', String(20), nullable=False, index=True),
    Column('owner', String(40), nullable=False),
    Column('attempt_token', String(36)),
    Column('started_at', String(32)),
    Column('finished_at', String(32)),
    Column('created_at', String(32), nullable=False),
    Column('error', Text))
evidence = Table('business_evidence', schema,
    Column('id', Integer, primary_key=True),
    Column('run_id', ForeignKey('business_runs.id'), nullable=False, unique=True),
    Column('report', JSON, nullable=False),
    Column('digest', String(64), nullable=False),
    Column('reviewer', String(40)),
    Column('review_note', String(500)),
    Column('reviewed_at', String(32)))
audit = Table('audit_events', schema,
    Column('id', Integer, primary_key=True),
    Column('actor', String(40), nullable=False),
    Column('action', String(32), nullable=False),
    Column('reference', String(50), nullable=False),
    Column('created_at', String(32), nullable=False))
warehouse = Table('warehouse_stock', schema,
    Column('ingredient', String(32), primary_key=True),
    Column('on_hand', String(40), nullable=False),
    Column('updated_at', String(32), nullable=False))
occupations = Table('stock_occupations', schema,
    Column('id', Integer, primary_key=True),
    Column('case_id', ForeignKey('business_cases.id'), nullable=False, index=True),
    Column('ingredient', String(32), nullable=False),
    Column('quantity', String(40), nullable=False),
    Column('status', String(20), nullable=False),
    Column('created_at', String(32), nullable=False),
    Column('released_at', String(32)),
    UniqueConstraint('case_id', 'ingredient', name='uq_occupation_case_ingredient'),
    Index('ix_occupation_ingredient', 'ingredient', 'status'))
orders = Table('purchase_orders', schema,
    Column('id', Integer, primary_key=True),
    Column('case_id', ForeignKey('business_cases.id'), nullable=False, unique=True),
    Column('payload', JSON, nullable=False),
    Column('digest', String(64), nullable=False),
    Column('created_at', String(32), nullable=False))
case_voids = Table('case_voids', schema,
    Column('case_id', ForeignKey('business_cases.id'), primary_key=True),
    Column('actor', String(40), nullable=False),
    Column('created_at', String(32), nullable=False))
