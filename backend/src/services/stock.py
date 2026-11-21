"""Shared warehouse occupation, purchase orders and batch voiding.

Quantities are stored as decimal text and computed in Python so retry,
void and read-back never lose precision. Every batch-scoped mutation first
locks the menu batch row, which serializes occupation, issuing and voiding
of the same batch. Different batches only contend on the ingredient rows
they actually share, so a batch that is still running never blocks another
batch from finishing and issuing its order.
"""

import hashlib
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select

from src.config.settings import engine
from src.models.tables import case_voids, cases, occupations, orders, warehouse
from src.utils.encoding import canonical
from src.utils.quantity import ZERO, allocate, text_of
from src.utils.time import utc_time

ACTIVE = "active"
RELEASED = "released"


def _dec(value):
    return Decimal(str(value))


def lock_case(conn, case_id):
    """Lock the menu batch row; every batch-scoped mutation takes this first."""
    row = conn.execute(select(cases.c.id).where(cases.c.id == case_id).with_for_update()).first()
    if row is None:
        raise ValueError("菜单批次不存在。")


def is_void(conn, case_id):
    return conn.execute(
        select(case_voids.c.case_id).where(case_voids.c.case_id == case_id)
    ).first() is not None


def register_declaration(conn, declared):
    """Merge one batch's stock fill into the shared warehouse.

    Each batch fills inventory independently and the same physical bag may
    appear in several fills, so the warehouse keeps the largest visible
    quantity declared for an ingredient instead of summing the fills.
    """
    for code in sorted(declared):
        quantity = declared[code]
        row = conn.execute(
            select(warehouse.c.on_hand).where(warehouse.c.ingredient == code).with_for_update()
        ).first()
        if row is None:
            conn.execute(warehouse.insert().values(
                ingredient=code, on_hand=text_of(quantity), updated_at=utc_time()))
        elif quantity > _dec(row.on_hand):
            conn.execute(warehouse.update().where(warehouse.c.ingredient == code)
                         .values(on_hand=text_of(quantity), updated_at=utc_time()))


def occupy(conn, case_id, code, declared, demand):
    """Occupy one ingredient for the batch; safe to retry at any time.

    Returns (quantity, snapshot). An existing active occupation is reused
    as is, so a retried run never occupies twice. Once the batch has an
    issued purchase order the books are closed and nothing new is occupied.
    Locking reads keep the remaining stock check and the insert atomic
    against other batches drawing from the same warehouse.
    """
    lock_case(conn, case_id)
    if is_void(conn, case_id):
        raise ValueError("该菜单批次已作废，无法继续备料。")
    mine = conn.execute(select(occupations.c.quantity).where(
        occupations.c.case_id == case_id,
        occupations.c.ingredient == code,
        occupations.c.status == ACTIVE,
    ).with_for_update()).first()
    row = conn.execute(
        select(warehouse.c.on_hand).where(warehouse.c.ingredient == code).with_for_update()
    ).first()
    on_hand = _dec(row.on_hand) if row else ZERO
    others = sum((_dec(item.quantity) for item in conn.execute(
        select(occupations.c.quantity).where(
            occupations.c.ingredient == code,
            occupations.c.status == ACTIVE,
            occupations.c.case_id != case_id,
        ).with_for_update())), ZERO)
    if mine is not None:
        quantity = _dec(mine.quantity)
    elif conn.execute(select(orders.c.id).where(orders.c.case_id == case_id)).first():
        quantity = ZERO
    else:
        quantity = allocate(demand, declared, on_hand - others)
        if quantity > ZERO:
            conn.execute(occupations.insert().values(
                case_id=case_id, ingredient=code, quantity=text_of(quantity),
                status=ACTIVE, created_at=utc_time()))
    return quantity, {
        "on_hand": on_hand,
        "others": others,
        "left": on_hand - others - quantity,
    }


def issue(conn, case_id, rows):
    """Issue the batch's purchase order once; later calls read it back as is.

    Returns (order_id, created_at, rows, freshly_issued).
    """
    lock_case(conn, case_id)
    if is_void(conn, case_id):
        raise ValueError("该菜单批次已作废，无法出单。")
    existing = conn.execute(select(orders).where(orders.c.case_id == case_id)).mappings().first()
    if existing is not None:
        return existing["id"], existing["created_at"], existing["payload"], False
    digest = hashlib.sha256(canonical(rows)).hexdigest()
    created = utc_time()
    order_id = conn.execute(orders.insert().values(
        case_id=case_id, payload=rows, digest=digest, created_at=created)
    ).inserted_primary_key[0]
    return order_id, created, rows, True


def void(conn, case_id, actor):
    """Void the batch and release its occupations for other batches.

    Issued purchase orders are deliberately left untouched so they read
    back exactly as issued.
    """
    conn.execute(case_voids.insert().values(case_id=case_id, actor=actor, created_at=utc_time()))
    conn.execute(occupations.update().where(
        occupations.c.case_id == case_id, occupations.c.status == ACTIVE
    ).values(status=RELEASED, released_at=utc_time()))


def warehouse_state():
    """Live per-ingredient view: on hand, occupied by whom, still available."""
    with engine.connect() as conn:
        rows = conn.execute(select(warehouse).order_by(warehouse.c.ingredient)).mappings().all()
        active = conn.execute(
            select(occupations.c.ingredient, occupations.c.case_id, occupations.c.quantity)
            .where(occupations.c.status == ACTIVE)
            .order_by(occupations.c.ingredient, occupations.c.case_id)
        ).mappings().all()
    holders = defaultdict(list)
    totals = defaultdict(lambda: ZERO)
    for row in active:
        holders[row["ingredient"]].append({"case_id": row["case_id"], "quantity": row["quantity"]})
        totals[row["ingredient"]] += _dec(row["quantity"])
    return [{
        "ingredient": row["ingredient"],
        "on_hand": row["on_hand"],
        "occupied": text_of(totals[row["ingredient"]]),
        "available": text_of(_dec(row["on_hand"]) - totals[row["ingredient"]]),
        "holders": holders[row["ingredient"]],
    } for row in rows]
