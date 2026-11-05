# 0001: Use the Olist e-commerce dataset

**Status:** Accepted

## Decision

Use the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) as the demo dataset. It has about 100,000 orders from 2016 to 2018 across related tables.

## Why

- Its multi-table schema tests SQL generation better than a single wide table.
- It supports common business questions about revenue, categories, delivery, and reviews.
- It's small enough to load in under a minute, and it needs no Kaggle account.

NYC taxi data was rejected because it offers few joins. The Lahman baseball database was rejected because questions need baseball knowledge.

## Consequences

- **Licence:** The data is CC BY-NC-SA 4.0, so it's non-commercial and share-alike, and it needs attribution. Raw files aren't committed. Revisit this choice before any commercial use.
- **Reproducibility:** The seed script checks each CSV against a pinned SHA-256 hash and stops if one differs. If the download URL stops working, place the archive at `db/seed/data/olist.zip` and run the seed again.

## Changes from the source data

- `product_name_lenght` and `product_description_lenght` are renamed to fix the spelling.
- Two categories missing from the translation file get English names.
- Raw geolocation has 1,000,163 rows. It's reduced to one row per zip prefix so joins can't multiply rows. Coordinates are medians, and city and state are the most common values. Seven prefixes still fall outside a rough bounding box around Brazil.
