from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from src.config.settings import IS_MYSQL, engine
from src.constants.workflow import Role
from src.models.tables import (audit, cases, evidence, occupations, orders,
                               runs, schema, users, warehouse)
from src.services import stock
from src.services.domain import SPEC, stock_declaration
from src.services.security import hash_password
from src.utils.time import utc_time

# 晚餐批次：与午餐填报同一份库存（同一袋料两边都算），从同一仓领料。
DINNER = {
    'batch': '砚街食堂 11月21日晚餐',
    'menu': [
        {'line': 'L11', 'recipe': 'C01', 'servings': 90},
        {'line': 'L12', 'recipe': 'C02', 'servings': 60},
    ],
    'recipes': SPEC['sample']['recipes'],
    'ingredients': SPEC['sample']['ingredients'],
    'components': SPEC['sample']['components'],
}


def keep_existing(conn, table, key, values):
    if IS_MYSQL:
        statement = mysql_insert(table).values(**values).on_duplicate_key_update(id=table.c.id)
    else:
        statement = postgres_insert(table).values(**values).on_conflict_do_nothing(index_elements=[key])
    conn.execute(statement)


def seed():
    with engine.begin() as conn:
        for role in Role:
            keep_existing(conn, users, 'username', {'username': role.value, 'role': role.value,
                'password_hash': hash_password('Demo-Walkthrough-2026')})
        keep_existing(conn, cases, 'slug', {'slug': 'demo', 'title': SPEC['name'],
            'payload': SPEC['sample'], 'author': 'demo', 'created_at': utc_time()})
        keep_existing(conn, cases, 'slug', {'slug': 'demo-dinner', 'title': f"{SPEC['name']}·晚餐",
            'payload': DINNER, 'author': 'demo', 'created_at': utc_time()})
        stock.register_declaration(conn, stock_declaration(SPEC['sample']))
        stock.register_declaration(conn, stock_declaration(DINNER))
        return {table.name: conn.execute(select(func.count()).select_from(table)).scalar_one()
                for table in (users, cases, runs, evidence, audit, warehouse, occupations, orders)}


if __name__ == '__main__':
    schema.create_all(engine)
    print(seed())
