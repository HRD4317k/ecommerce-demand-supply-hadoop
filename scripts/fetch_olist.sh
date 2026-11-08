#!/usr/bin/env bash
# Download the real Olist dataset into data/raw/olist (about 60 MB, not committed to git).
#
# Preferred: the official Kaggle copy (needs a free Kaggle account + API token, `pip install kaggle`).
# Fallback : a public GitHub mirror of the same nine CSV files (the one this project was developed against;
#            pinned to the commit below and checked against known row counts).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$ROOT/data/raw/olist}"
MIRROR="https://github.com/iiaauu456-boop/brazilian-olist-e-commerce-dataset"
MIRROR_COMMIT="b93633e64c66585db48ee6afcdd1582aff3bef4c"

if [ -f "$DEST/olist_orders_dataset.csv" ]; then echo "already present in $DEST"; exit 0; fi
mkdir -p "$DEST"
if command -v kaggle >/dev/null 2>&1 && [ -n "${KAGGLE_USERNAME:-}${KAGGLE_CONFIG_DIR:-}" -o -f "$HOME/.kaggle/kaggle.json" ]; then
  echo "downloading from Kaggle (olistbr/brazilian-ecommerce)"
  kaggle datasets download -d olistbr/brazilian-ecommerce -p "$DEST" --unzip
else
  echo "Kaggle CLI not configured, using the GitHub mirror $MIRROR @ ${MIRROR_COMMIT:0:7}"
  tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
  GIT_LFS_SKIP_SMUDGE=1 git clone --quiet "$MIRROR" "$tmp/m"
  git -C "$tmp/m" checkout --quiet "$MIRROR_COMMIT"
  cp "$tmp/m"/*.csv "$DEST/"
fi

# sanity check: the official files have these line counts (header included)
check() { local n; n=$(wc -l < "$DEST/$1"); [ "$n" -ge "$2" ] || { echo "$1 has $n lines, expected about $2" >&2; exit 1; }; }
check olist_orders_dataset.csv 99000
check olist_order_items_dataset.csv 112000
check olist_products_dataset.csv 32000
check olist_sellers_dataset.csv 3000
echo "ok: Olist data in $DEST"
