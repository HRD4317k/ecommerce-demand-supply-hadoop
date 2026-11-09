PY ?= python3
RAW ?= data/raw/olist

.PHONY: install fetch real demo test clean hadoop hadoop-standalone hive-check
install:
	$(PY) -m pip install -r requirements.txt

fetch:           ## download the real Olist dataset into data/raw/olist
	scripts/fetch_olist.sh $(RAW)

real: fetch      ## REAL data: Olist marketplace orders -> data/olist, run everything -> out/olist, reports/
	$(PY) src/datagen/prepare_olist.py --raw $(RAW) --out data/olist
	DATA_DIR=data/olist OUT_DIR=out/olist REPORTS_DIR=reports scripts/run_local.sh

demo:            ## synthetic data with planted patterns (no download needed) -> data/synthetic, out/synthetic, reports/synthetic
	$(PY) src/datagen/generate.py --out data/synthetic
	DATA_DIR=data/synthetic OUT_DIR=out/synthetic REPORTS_DIR=reports/synthetic scripts/run_local.sh

test:
	$(PY) -m pytest -q

hadoop:          ## same pipeline on a cluster (needs hadoop + hdfs on PATH; see README for what has been verified)
	scripts/run_hadoop.sh

hadoop-standalone: ## build Hadoop 3.3.4 (standalone), run all jobs through real Hadoop Streaming, compare with the local runner
	scripts/setup_hadoop_standalone.sh
	mkdir -p out/olist_hadoop
	HADOOP_HOME=$(CURDIR)/.hadoop PATH=$(CURDIR)/.hadoop/bin:$$PATH DATA_DIR=data/olist OUT_DIR=out/olist_hadoop \
	  HDFS_BASE=$(CURDIR)/out/hdfs REPORTS_DIR=out/olist_hadoop/reports scripts/run_hadoop.sh
	$(PY) src/analysis/hadoop_summary.py --hadoop out/olist_hadoop --local out/olist --reports reports

hive-check:      ## run hive/*.hql with Spark SQL and compare with the MapReduce output (pip install pyspark py4j)
	$(PY) scripts/check_hive_sql.py --raw out/hdfs/raw --mr out/olist_hadoop --meta data/olist/meta.json

clean:
	rm -rf out data/olist data/synthetic .pytest_cache
