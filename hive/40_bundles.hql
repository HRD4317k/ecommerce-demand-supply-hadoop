-- Idea 7: bundle mining (support, confidence, lift) as one SQL self-join.
-- The MapReduce version (src/jobs/cooccur_*.py) shows the "pairs" pattern step by step.
-- Usage: hive --hivevar min_pairs=15 -f hive/40_bundles.hql
USE ecom;

CREATE TABLE IF NOT EXISTS bundles STORED AS ORC AS
WITH n AS (SELECT COUNT(DISTINCT order_id) AS total FROM orders),
item AS (SELECT sku, COUNT(DISTINCT order_id) AS c FROM orders GROUP BY sku),
pair AS (
  SELECT a.sku AS sku_a, b.sku AS sku_b, COUNT(DISTINCT a.order_id) AS pair_orders
  FROM orders a JOIN orders b ON a.order_id = b.order_id AND a.sku < b.sku
  GROUP BY a.sku, b.sku
)
SELECT p.sku_a, p.sku_b, p.pair_orders,
       p.pair_orders / n.total AS support,
       p.pair_orders / ia.c AS conf_a_to_b,
       p.pair_orders / ib.c AS conf_b_to_a,
       p.pair_orders * n.total / (ia.c * ib.c) AS lift
FROM pair p
JOIN item ia ON p.sku_a = ia.sku
JOIN item ib ON p.sku_b = ib.sku
CROSS JOIN n
WHERE p.pair_orders >= ${hivevar:min_pairs};
