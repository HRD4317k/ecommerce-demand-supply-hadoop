# Data: what is real, what is assumed

## Source

**Brazilian E-Commerce Public Dataset by Olist** (Kaggle listing `olistbr/brazilian-ecommerce`): real, anonymised
orders from a Brazilian marketplace, placed 2016-2018. Licence CC BY-NC-SA 4.0 (non-commercial, share-alike, attribution),
so the files are downloaded on demand by `scripts/fetch_olist.sh` and are not stored in this repository.

The workspace used for development could not reach Kaggle, so it used a public GitHub mirror of the nine CSV files
(`iiaauu456-boop/brazilian-olist-e-commerce-dataset`, commit `b93633e`). Row counts match the official release
(99,441 orders; 112,650 order items; 32,951 products; 3,095 sellers). SHA-256 of the main files, to check your copy:

| file | sha256 |
|---|---|
| olist_orders_dataset.csv | 8df58ef3d2d7e9944010f7beecd9b75367f5588ec6e3c91cec19ae3345ef9ecf |
| olist_order_items_dataset.csv | 0bc4d068c4fe38cbb01bd90e8746e3c613fe7b4baef75fab7b0e329701c3e279 |
| olist_products_dataset.csv | 3e6569628a17fbc75fd206ee357b59e20364b9afa90f5b6cd5b4d624c58aa9cc |
| olist_customers_dataset.csv | 983a422239e1712ded753b3bf9ecf47dc73f144d306029dcfa99e70a226883d2 |
| olist_sellers_dataset.csv | 1f643d2b950373b85735e7794b20986f528d7a000432e7c6f9bcbb44d0846a0e |

## What `src/datagen/prepare_olist.py` does

| Output | Built from | Real or assumed |
|---|---|---|
| `orders.csv` (96k orders, 97k lines) | order + item + product + customer tables; 2017-01-01 to the last stable day (2018-08-21) | **real** |
| `returns.csv` (433 lines) | orders with status `canceled` / `unavailable` that have items | **real cancellations**; the dataset has no returns, and no cancel date, so they are booked on the order day |
| `deliveries.csv` (96k lines) | per (order, seller, category): purchase date, estimated delivery date, real delivery date | **real** |
| `baskets_products.csv` | the same baskets at product level, for bundle mining | **real** |
| `inventory.csv` (93 category-hub pairs) | seeded "days of cover" snapshot on top of the real demand of the last 28 days; primary supplier = the seller with most lines in that pair | **ASSUMED** (no public dataset has warehouse stock) |
| `meta.json` `lanes` | cost per unit and days between the 5 hubs | **ASSUMED** |

Mapping decisions you may want to change (all at the top of `prepare_olist.py`):

- **SKU = product category**, because individual products sell far too rarely to forecast (the best product sells about
  0.9 units a day). 71 categories are grouped into 7 departments (`DEPARTMENT`).
- **Warehouse = regional hub** from the customer state: SP, RJ (RJ+ES), MG (MG+centre-west), SUL (RS+PR+SC), NE (all others).
- **Supplier lead time = the seller's observed order-to-delivery time.** In a marketplace the seller ships straight to the
  customer, so this is the closest real proxy for replenishment lead time. The "quote" is the estimate Olist showed the customer.
- **Sale = Black Friday 2017** (2017-11-24 to 2017-11-30); the data itself shows the spike (1,176 orders on the day against
  roughly 200 on a normal day).
- **As-of date = 2018-08-21**, detected as the last day whose volume is still normal; the final days of the dataset are thin.

## Findings that come from the data and are worth knowing

- Delivery estimates are padded: observed delivery is about 12 days faster than quoted on average.
- 96.7% of orders contain a single product (0.7% span two categories), so bundle mining has little to find.
- Cancellations are about 0.5% of units: returns-adjusted demand barely moves the numbers on this dataset.
- A history-based forecast cannot see a promotion coming: when Black Friday starts inside the forecast window every method under-forecasts by roughly 50-65%.

## Synthetic demo data

`src/datagen/generate.py` writes the same four files with planted patterns (six bundle pairs, a 1.9x sale, returns by
category, suppliers with optimistic quotes). It exists for demos and tests: `make demo`.
