-- Idea 6: supplier scorecard (same formulas as src/jobs/supplier_reduce.py).
-- Usage: hive -f hive/20_supplier_scorecard.hql
USE ecom;

CREATE TABLE IF NOT EXISTS supplier_stats STORED AS ORC AS
SELECT supplier_id, n_pos, on_time_rate, avg_delay_days, lead_mean, lead_std, fill_rate, score,
       CASE WHEN score >= 85 THEN 'A' WHEN score >= 70 THEN 'B' ELSE 'C' END AS tier
FROM (
  SELECT supplier_id, n_pos, on_time_rate, avg_delay_days, lead_mean, lead_std, fill_rate,
         100 * (0.4 * on_time_rate + 0.4 * LEAST(1.0, fill_rate)
                + 0.2 * (1 - LEAST(1.0, lead_std / lead_mean))) AS score
  FROM (
    SELECT supplier_id,
           COUNT(*) AS n_pos,
           AVG(CASE WHEN delivered_date <= promised_date THEN 1.0 ELSE 0.0 END) AS on_time_rate,
           AVG(datediff(delivered_date, promised_date)) AS avg_delay_days,
           AVG(datediff(delivered_date, order_date)) AS lead_mean,
           STDDEV_POP(datediff(delivered_date, order_date)) AS lead_std,
           SUM(qty_received) / SUM(qty_ordered) AS fill_rate
    FROM deliveries
    GROUP BY supplier_id
  ) s
) t;
