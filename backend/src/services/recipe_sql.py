"""Read-only MySQL query for one menu batch."""

from sqlalchemy import text


# Depth 8 and three fractional places per ratio require 24 fractional places.
# The string path stores at most nine integer IDs, each at most three digits.
EXPAND_RECIPES = text("""
    WITH RECURSIVE
    menu AS (
        SELECT line_id, recipe_id, servings
        FROM JSON_TABLE(:menu, '$[*]' COLUMNS (
            line_id FOR ORDINALITY,
            recipe_id INT PATH '$.recipe_id',
            servings INT PATH '$.servings'
        )) AS input_menu
    ),
    edges AS (
        SELECT parent_id, child_id, ratio
        FROM JSON_TABLE(:edges, '$[*]' COLUMNS (
            parent_id INT PATH '$.parent_id',
            child_id INT PATH '$.child_id',
            ratio DECIMAL(6, 3) PATH '$.ratio'
        )) AS input_edges
    ),
    recipe_parents AS (
        SELECT DISTINCT parent_id FROM edges
    ),
    walk (line_id, node_id, depth, path_ids, quantity, is_cycle) AS (
        SELECT line_id, recipe_id, 0, CAST(recipe_id AS CHAR(40)),
               CAST(servings AS DECIMAL(52, 24)), 0
        FROM menu
        UNION ALL
        SELECT walk.line_id, edges.child_id, walk.depth + 1,
               CONCAT(walk.path_ids, ',', edges.child_id),
               CAST(walk.quantity * edges.ratio AS DECIMAL(52, 24)),
               FIND_IN_SET(edges.child_id, walk.path_ids) > 0
        FROM walk
        JOIN edges ON edges.parent_id = walk.node_id
        WHERE walk.is_cycle = 0 AND walk.depth < :max_depth
        LIMIT :row_limit
    ),
    classified AS (
        SELECT walk.*,
            CASE
                WHEN is_cycle = 1 THEN 'cycle'
                WHEN node_id > :recipe_count THEN 'material'
                WHEN recipe_parents.parent_id IS NULL THEN 'missing'
                WHEN depth = :max_depth THEN 'depth'
            END AS kind
        FROM walk
        LEFT JOIN recipe_parents ON recipe_parents.parent_id = walk.node_id
    ),
    terminals AS (
        SELECT kind, line_id, node_id, path_ids, quantity
        FROM classified
        WHERE kind IS NOT NULL
    ),
    blocked_lines AS (
        SELECT DISTINCT line_id FROM terminals WHERE kind <> 'material'
    )
    SELECT 'budget' AS kind, NULL AS line_id, NULL AS node_id,
           NULL AS path_ids, NULL AS quantity, COUNT(*) AS path_count,
           NULL AS menu_count
    FROM walk
    UNION ALL
    SELECT kind, line_id, node_id, path_ids, quantity, NULL, NULL
    FROM terminals
    UNION ALL
    SELECT 'total', NULL, terminals.node_id, NULL, SUM(terminals.quantity),
           COUNT(*), COUNT(DISTINCT terminals.line_id)
    FROM terminals
    LEFT JOIN blocked_lines ON blocked_lines.line_id = terminals.line_id
    WHERE terminals.kind = 'material' AND blocked_lines.line_id IS NULL
    GROUP BY terminals.node_id
    ORDER BY kind, line_id, node_id, path_ids
""")
