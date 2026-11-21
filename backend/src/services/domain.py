"""Expand menu recipes and produce a purchase proposal with path evidence."""

import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext

from .recipe_sql import EXPAND_RECIPES


MAX_DEPTH = 8
MAX_WALK_ROWS = 20_000
INPUT_STEP = Decimal("0.001")
CODE = re.compile(r"[A-Za-z0-9_-]{1,32}")

SPEC = {
    "name": "砚街食堂·团餐备料展开",
    "summary": "从午餐菜单展开半成品配方，合并原料需求并按库存和包装规格生成采购备料单。",
    "customer": "砚街食堂团餐中心·生产计划组",
    "entity_labels": ["菜单批次", "原料展算", "采购备料单"],
    "field_labels": {
        "batch": "菜单批次",
        "menu": "菜单行",
        "recipes": "菜品与半成品",
        "ingredients": "采购原料",
        "components": "配方明细",
        "line": "菜单行编号",
        "recipe": "配方编号",
        "ingredient": "原料编号",
        "servings": "计划份数",
        "name": "品名",
        "unit": "计量单位",
        "stock": "本批可用库存",
        "pack": "每包数量",
        "parent": "上级配方编号",
        "component": "下级配方或原料编号",
        "qty": "每单位上级产出耗用量",
    },
    "guidance": "填写菜单份数、单位产出耗用量和本批可用库存。先处理冻结菜品，再按已通过菜品的备料单核对采购包数。",
    "sample": {
        "batch": "砚街食堂 11月21日午餐",
        "menu": [
            {"line": "L01", "recipe": "C01", "servings": 120},
            {"line": "L02", "recipe": "C02", "servings": 80},
            {"line": "L03", "recipe": "C03", "servings": 30},
        ],
        "recipes": [
            {"recipe": "C01", "name": "葱油拌面", "unit": "份"},
            {"recipe": "C02", "name": "茴香蒸卷", "unit": "份"},
            {"recipe": "C03", "name": "试做酱拌面", "unit": "份"},
            {"recipe": "R01", "name": "手工鲜面", "unit": "kg"},
            {"recipe": "R02", "name": "葱油汁", "unit": "kg"},
            {"recipe": "R03", "name": "基础面团", "unit": "kg"},
            {"recipe": "R04", "name": "卷坯", "unit": "kg"},
            {"recipe": "R05", "name": "试做酱", "unit": "kg"},
            {"recipe": "R06", "name": "回锅底酱", "unit": "kg"},
        ],
        "ingredients": [
            {"ingredient": "M01", "name": "小麦粉", "unit": "kg", "stock": 15, "pack": 5},
            {"ingredient": "M02", "name": "大豆油", "unit": "kg", "stock": 1.6, "pack": 2},
            {"ingredient": "M03", "name": "香葱", "unit": "kg", "stock": 0.6, "pack": 0.5},
            {"ingredient": "M04", "name": "食盐", "unit": "kg", "stock": 0.5, "pack": 1},
            {"ingredient": "M05", "name": "茴香", "unit": "kg", "stock": 2, "pack": 1},
        ],
        "components": [
            {"parent": "C01", "component": "R01", "qty": 0.18},
            {"parent": "C01", "component": "R02", "qty": 0.025},
            {"parent": "C02", "component": "R04", "qty": 0.125},
            {"parent": "C02", "component": "R02", "qty": 0.015},
            {"parent": "C03", "component": "R01", "qty": 0.16},
            {"parent": "C03", "component": "R05", "qty": 0.03},
            {"parent": "R01", "component": "R03", "qty": 1},
            {"parent": "R04", "component": "R03", "qty": 1},
            {"parent": "R04", "component": "M05", "qty": 0.1},
            {"parent": "R03", "component": "M01", "qty": 0.8},
            {"parent": "R03", "component": "M04", "qty": 0.01},
            {"parent": "R02", "component": "M01", "qty": 0.05},
            {"parent": "R02", "component": "M02", "qty": 0.7},
            {"parent": "R02", "component": "M03", "qty": 0.15},
            {"parent": "R05", "component": "R06", "qty": 0.5},
            {"parent": "R06", "component": "R05", "qty": 0.2},
            {"parent": "R06", "component": "M02", "qty": 0.1},
        ],
    },
    "expect": {"已核菜单行": 2, "冻结菜单行": 1, "共用原料": 4, "需采购原料": 3},
}

ISSUES = {
    "cycle": ("配方循环", "复核闭环中的配方用料，修正回指明细后重算。"),
    "missing": ("配方未维护", "补录该配方的用料明细后重算。"),
    "depth": ("超过展开层数", f"复核末级配方并将链路控制在 {MAX_DEPTH} 层内。"),
}


def _rows(payload, key, lower, upper):
    rows = payload.get(key)
    label = SPEC["field_labels"][key]
    if not isinstance(rows, list) or not lower <= len(rows) <= upper:
        raise ValueError(f"{label}须为 {lower} 至 {upper} 行的数组。")
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{label}中的每一行都须为对象。")
    return rows


def _text(row, key, maximum):
    value = row.get(key)
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError(f"{SPEC['field_labels'][key]}须填写 1 至 {maximum} 个字符。")
    return value.strip()


def _code(value, label):
    if not isinstance(value, str) or not CODE.fullmatch(value):
        raise ValueError(f"{label}须为 1 至 32 位字母、数字、连字符或下划线。")
    return value


def _decimal(value, label, maximum, *, allow_zero=False):
    message = f"{label}须为{'非负数' if allow_zero else '正数'}，不超过 {maximum}，最多三位小数。"
    if type(value) not in (int, float, str):
        raise ValueError(message)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(message) from error
    minimum = 0 if allow_zero else INPUT_STEP
    if not number.is_finite() or not minimum <= number <= maximum:
        raise ValueError(message)
    rounded = number.quantize(INPUT_STEP)
    if rounded != number:
        raise ValueError(message)
    return rounded.copy_abs()


def _prepare(payload):
    if not isinstance(payload, dict):
        raise ValueError("菜单批次须为对象。")
    batch = _text(payload, "batch", 100)
    recipes = _rows(payload, "recipes", 1, 500)
    ingredients = _rows(payload, "ingredients", 0, 500)
    menu = _rows(payload, "menu", 1, 200)
    components = _rows(payload, "components", 0, 2000)
    if len(recipes) + len(ingredients) > 500:
        raise ValueError("菜品、半成品和原料合计最多 500 项。")

    nodes = {}
    for key, rows in (("recipe", recipes), ("ingredient", ingredients)):
        for row in rows:
            code = _code(row.get(key), SPEC["field_labels"][key])
            if code in nodes:
                raise ValueError(f"物料编号 {code} 重复。")
            node = {
                "code": code,
                "id": len(nodes) + 1,
                "name": _text(row, "name", 80),
                "unit": _text(row, "unit", 12),
            }
            if key == "ingredient":
                node["stock"] = _decimal(row.get("stock"), f"{code} 库存", 1_000_000, allow_zero=True)
                node["pack"] = _decimal(row.get("pack"), f"{code} 包装量", 1_000_000)
            nodes[code] = node

    menu_input = []
    line_codes = set()
    for row in menu:
        line = _code(row.get("line"), "菜单行编号")
        recipe = _code(row.get("recipe"), "菜单配方编号")
        if line in line_codes:
            raise ValueError(f"菜单行编号 {line} 重复。")
        line_codes.add(line)
        if recipe not in nodes or nodes[recipe]["id"] > len(recipes):
            raise ValueError(f"菜单行 {line} 的配方 {recipe} 未登记。")
        if nodes[recipe]["unit"] != "份":
            raise ValueError(f"菜单行 {line} 的配方 {recipe} 须以份为产出单位。")
        servings = row.get("servings")
        if type(servings) is not int or not 1 <= servings <= 100_000:
            raise ValueError(f"菜单行 {line} 的计划份数须为 1 至 100000 的整数。")
        menu_input.append({"line": line, "recipe_id": nodes[recipe]["id"], "servings": servings})

    edges = []
    pairs = set()
    for row in components:
        parent = _code(row.get("parent"), "上级配方编号")
        child = _code(row.get("component"), "下级配方或原料编号")
        if parent not in nodes or nodes[parent]["id"] > len(recipes):
            raise ValueError(f"上级编号 {parent} 须为已登记的配方。")
        if child not in nodes:
            raise ValueError(f"配方 {parent} 引用未登记编号 {child}。")
        if (parent, child) in pairs:
            raise ValueError(f"配方 {parent} 内的用料 {child} 重复，请合并耗用量。")
        pairs.add((parent, child))
        ratio = _decimal(row.get("qty"), f"{parent} → {child} 耗用量", 100)
        edges.append({"parent_id": nodes[parent]["id"], "child_id": nodes[child]["id"], "ratio": _quantity(ratio)})

    return batch, menu_input, nodes, edges, len(recipes)


def validate(payload):
    _prepare(payload)


def _quantity(number):
    fixed = format(number, "f")
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def _label(node):
    return f"{node['name']}（{node['code']}）"


def _purchase_row(node, row):
    gross = row["quantity"]
    stock, pack = node["stock"], node["pack"]
    with localcontext() as context:
        context.prec = 60
        shortage = max(gross - stock, Decimal(0))
        packages, remainder = divmod(shortage, pack)
        packages = int(packages) + int(remainder > 0)
        order_quantity = packages * pack
    return {
        "原料编号": node["code"], "原料": node["name"], "单位": node["unit"],
        "需求量": _quantity(gross), "可用库存": _quantity(stock), "缺口": _quantity(shortage),
        "每包数量": _quantity(pack), "建议包数": str(packages), "建议采购量": _quantity(order_quantity),
        "来源菜单行数": row["menu_count"], "计入路径数": row["path_count"],
        "采购判定": "按包补货" if packages else "库存够用",
    }


def solve(payload, engine):
    batch, menu, nodes, edges, recipe_count = _prepare(payload)
    with engine.begin() as conn:
        rows = conn.execute(EXPAND_RECIPES, {
            "menu": json.dumps(menu),
            "edges": json.dumps(edges),
            "recipe_count": recipe_count,
            "max_depth": MAX_DEPTH,
            "row_limit": MAX_WALK_ROWS + 1,
        }).mappings().all()

    budget = next(row for row in rows if row["kind"] == "budget")
    if budget["path_count"] > MAX_WALK_ROWS:
        raise ValueError(f"配方展开超过 {MAX_WALK_ROWS} 条记录，无法核准采购量。请检查配方并缩小核算批次。")

    by_id = {node["id"]: node for node in nodes.values()}
    ratios = {(edge["parent_id"], edge["child_id"]): edge["ratio"] for edge in edges}
    blocked = Counter(row["line_id"] for row in rows if row["kind"] in ISSUES)
    menu_rows = [
        {
            "菜单行": item["line"], "菜品": _label(by_id[item["recipe_id"]]),
            "计划份数": item["servings"], "异常路径数": blocked[line_id],
            "核算状态": "冻结" if line_id in blocked else "通过",
        }
        for line_id, item in enumerate(menu, start=1)
    ]
    purchase, evidence, issues = [], [], []
    for row in rows:
        kind = row["kind"]
        if kind == "budget":
            continue
        node = by_id[row["node_id"]]
        if kind == "total":
            purchase.append(_purchase_row(node, row))
            continue
        path_ids = [int(value) for value in row["path_ids"].split(",")]
        path = [_label(by_id[node_id]) for node_id in path_ids]
        item = menu[row["line_id"] - 1]
        if kind == "material":
            factors = [str(item["servings"])]
            factors.extend(ratios[edge] for edge in zip(path_ids, path_ids[1:]))
            evidence.append({
                "菜单行": item["line"], "原料编号": node["code"], "单位": node["unit"],
                "配方路径": " → ".join(path), "路径算式": " × ".join(factors),
                "路径用量": _quantity(row["quantity"]),
                "采购口径": "冻结，未计入" if row["line_id"] in blocked else "已计入",
            })
        else:
            issue, action = ISSUES[kind]
            issues.append({
                "菜单行": item["line"], "异常": issue, "配方路径": " → ".join(path),
                "闭环": " → ".join(path[path_ids.index(path_ids[-1]):]) if kind == "cycle" else "",
                "处理动作": action,
            })

    purchase.sort(key=lambda item: item["原料编号"])
    approved = len(menu) - len(blocked)
    to_order = sum(row["采购判定"] == "按包补货" for row in purchase)
    purchase_summary = (
        f"已核菜品有 {to_order} 种原料需要补货。" if approved else "请修正配方后重算采购量。"
    )
    return {
        "summary": f"{batch}共 {len(menu)} 条菜单行，核准 {approved} 条，冻结 {len(blocked)} 条。"
                   f"{purchase_summary}",
        "metrics": {
            "已核菜单行": approved,
            "冻结菜单行": len(blocked),
            "共用原料": sum(row["来源菜单行数"] > 1 for row in purchase),
            "需采购原料": to_order,
        },
        "sections": [
            {"title": "采购备料单（已核菜单行）", "rows": purchase},
            {"title": "菜单行核算状态", "rows": menu_rows},
            {"title": "待修配方", "rows": issues},
            {"title": "原料用量路径", "rows": evidence},
        ],
    }
