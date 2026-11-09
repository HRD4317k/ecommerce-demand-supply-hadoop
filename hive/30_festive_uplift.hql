-- Idea 5: weekday-adjusted festive-sale uplift per department (same maths as src/jobs/uplift_reduce.py).
-- Days without orders count as 0 units, exactly like the MapReduce job: the sale calendar is generated, and
-- the 28-day baseline is divided by 28 (and by 4 per weekday: 28 days hold exactly four of each weekday).
-- Usage: hive --hivevar sale_start=2017-11-24 --hivevar sale_end=2017-11-30 -f hive/30_festive_uplift.hql
USE ecom;

CREATE TABLE IF NOT EXISTS festive_uplift STORED AS ORC AS
WITH daily AS (
  SELECT category, order_date AS d, SUM(qty) AS units
  FROM orders
  GROUP BY category, order_date
),
cats AS (SELECT DISTINCT category FROM orders),
sale_cal AS (                                                      -- every calendar day of the sale
  SELECT CAST(date_add('${hivevar:sale_start}', i) AS STRING) AS d
  FROM (SELECT posexplode(split(space(datediff('${hivevar:sale_end}', '${hivevar:sale_start}')), ' ')) AS (i, x)) t
),
base AS (                                                          -- 28 days before the sale, per weekday
  SELECT category,
         pmod(datediff(d, '1970-01-04'), 7) AS dow,                -- weekday number, 0 = Sunday
         SUM(units) / 4.0 AS base_units
  FROM daily
  WHERE d >= CAST(date_sub('${hivevar:sale_start}', 28) AS STRING) AND d < '${hivevar:sale_start}'
  GROUP BY category, pmod(datediff(d, '1970-01-04'), 7)
),
base_all AS (
  SELECT category, SUM(units) / 28.0 AS base_avg
  FROM daily
  WHERE d >= CAST(date_sub('${hivevar:sale_start}', 28) AS STRING) AND d < '${hivevar:sale_start}'
  GROUP BY category
),
sale AS (
  SELECT c.category, pmod(datediff(cal.d, '1970-01-04'), 7) AS dow, COALESCE(dl.units, 0) AS units
  FROM cats c CROSS JOIN sale_cal cal
  LEFT JOIN daily dl ON dl.category = c.category AND dl.d = cal.d
)
SELECT s.category,
       ba.base_avg AS base_avg_day,
       AVG(s.units) AS sale_avg_day,
       AVG(s.units) / ba.base_avg AS plain_ratio,
       AVG(CASE WHEN b.base_units > 0 THEN s.units / b.base_units END) AS uplift,   -- each sale day vs ITS weekday
       COUNT(*) AS sale_days
FROM sale s
LEFT JOIN base b ON s.category = b.category AND s.dow = b.dow
JOIN base_all ba ON s.category = ba.category
GROUP BY s.category, ba.base_avg;
