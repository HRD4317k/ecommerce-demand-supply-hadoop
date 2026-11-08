PY ?= python3
RAW ?= data/raw/olist

.PHONY: install fetch real demo test clean hadoop
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

hadoop:          ## same pipeline on a real cluster (untested here, see README)
	scripts/run_hadoop.sh

clean:
	rm -rf out data/olist data/synthetic .pytest_cache
