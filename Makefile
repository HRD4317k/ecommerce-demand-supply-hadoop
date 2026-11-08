PY ?= python3

.PHONY: install data run test clean hadoop
install:
	$(PY) -m pip install -r requirements.txt

data:            ## synthetic orders, returns, inventory, deliveries -> data/
	$(PY) src/datagen/generate.py --out data

run: data        ## whole pipeline locally (cat | map | sort | reduce) -> out/ and reports/
	scripts/run_local.sh

test:
	$(PY) -m pytest -q

hadoop:          ## same pipeline on a real cluster (untested here, see README)
	scripts/run_hadoop.sh

clean:
	rm -rf out data .pytest_cache
