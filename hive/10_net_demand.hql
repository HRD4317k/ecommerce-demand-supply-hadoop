-- Ideas 1 and 8: net daily demand per SKU and warehouse.
-- Orders count on the order date, returns on the day the goods come back
-- (same definition as src/jobs/daily_demand_map.py).
-- Usage: hive -f hive/10_net_demand.hql
USE ecom;

CREATE TABLE IF NOT EXISTS daily_demand STORED AS ORC AS
SELECT sku, warehouse, d AS demand_date,
       SUM(ordered) AS ordered, SUM(returned) AS returned, SUM(ordered) - SUM(returned) AS net
FROM (
  SELECT sku, warehouse, order_date AS d, qty AS ordered, 0 AS returned FROM orders
  UNION ALL
  SELECT sku, warehouse, return_date AS d, 0 AS ordered, qty AS returned FROM returns
) u
GROUP BY sku, warehouse, d;

-- Idea 8: return rate by category
SELECT o.category, o.units AS ordered, COALESCE(r.units, 0) AS returned,
       COALESCE(r.units, 0) / o.units AS return_rate
FROM (SELECT category, SUM(qty) AS units FROM orders GROUP BY category) o
LEFT JOIN (SELECT category, SUM(qty) AS units FROM returns GROUP BY category) r
  ON o.category = r.category
ORDER BY return_rate DESC;
