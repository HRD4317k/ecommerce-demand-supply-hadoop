-- Idea 5: weekday-adjusted festive-sale uplift per category (same maths as src/jobs/uplift_reduce.py).
-- Usage: hive --hivevar sale_start=2017-11-24 --hivevar sale_end=2017-11-30 -f hive/30_festive_uplift.hql
USE ecom;

CREATE TABLE IF NOT EXISTS festive_uplift STORED AS ORC AS
WITH daily AS (
  SELECT category, order_date AS d,
         pmod(datediff(order_date, '1970-01-04'), 7) AS dow,      -- weekday number, 0 = Sunday
         SUM(qty) AS units
  FROM orders
  GROUP BY category, order_date
),
base AS (                                                          -- 28 days before the sale
  SELECT category, dow, AVG(units) AS base_units
  FROM daily
  WHERE d >= date_sub('${hivevar:sale_start}', 28) AND d < '${hivevar:sale_start}'
  GROUP BY category, dow
),
base_all AS (
  SELECT category, AVG(units) AS base_avg
  FROM daily
  WHERE d >= date_sub('${hivevar:sale_start}', 28) AND d < '${hivevar:sale_start}'
  GROUP BY category
),
sale AS (
  SELECT category, dow, units
  FROM daily
  WHERE d >= '${hivevar:sale_start}' AND d <= '${hivevar:sale_end}'
)
SELECT s.category,
       ba.base_avg AS base_avg_day,
       AVG(s.units) AS sale_avg_day,
       AVG(s.units) / ba.base_avg AS plain_ratio,
       AVG(s.units / b.base_units) AS uplift,                       -- each sale day vs ITS weekday
       COUNT(*) AS sale_days
FROM sale s
JOIN base b ON s.category = b.category AND s.dow = b.dow
JOIN base_all ba ON s.category = ba.category
GROUP BY s.category, ba.base_avg;
