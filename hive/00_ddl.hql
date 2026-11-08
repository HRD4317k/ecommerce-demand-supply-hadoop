-- Hive tables over the raw files that scripts/run_hadoop.sh puts on HDFS.
-- Reference SQL: these scripts mirror the MapReduce jobs but were NOT executed in this repository.
-- Column layouts match the files written by src/datagen/prepare_olist.py (real Olist data) and generate.py.
-- Usage: hive -f hive/00_ddl.hql

CREATE DATABASE IF NOT EXISTS ecom;
USE ecom;

CREATE EXTERNAL TABLE IF NOT EXISTS orders (
  order_id BIGINT, order_date STRING, sku STRING, category STRING,
  warehouse STRING, qty INT, price DOUBLE)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE LOCATION '/ecom/raw/orders'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS returns (
  return_id STRING, order_id BIGINT, sku STRING, category STRING,
  warehouse STRING, return_date STRING, qty INT, reason STRING)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE LOCATION '/ecom/raw/returns'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS inventory (
  sku STRING, warehouse STRING, on_hand INT, on_order INT,
  supplier_id STRING, nominal_lead_days INT)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE LOCATION '/ecom/raw/inventory'
TBLPROPERTIES ('skip.header.line.count'='1');

CREATE EXTERNAL TABLE IF NOT EXISTS deliveries (
  po_id STRING, supplier_id STRING, sku STRING, warehouse STRING,
  order_date STRING, promised_date STRING, delivered_date STRING,
  qty_ordered INT, qty_received INT)
ROW FORMAT DELIMITED FIELDS TERMINATED BY ','
STORED AS TEXTFILE LOCATION '/ecom/raw/deliveries'
TBLPROPERTIES ('skip.header.line.count'='1');
