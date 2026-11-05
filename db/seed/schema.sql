-- Olist e-commerce schema. Column comments record traps in the data, and the
-- schema service can pass them to the LLM later.

DROP TABLE IF EXISTS
  order_reviews,
  order_payments,
  order_items,
  orders,
  products,
  product_categories,
  sellers,
  customers,
  geolocation;

CREATE TABLE customers (
  customer_id TEXT PRIMARY KEY,
  customer_unique_id TEXT NOT NULL,
  customer_zip_code_prefix TEXT NOT NULL,
  customer_city TEXT NOT NULL,
  customer_state TEXT NOT NULL
);

CREATE TABLE sellers (
  seller_id TEXT PRIMARY KEY,
  seller_zip_code_prefix TEXT NOT NULL,
  seller_city TEXT NOT NULL,
  seller_state TEXT NOT NULL
);

CREATE TABLE product_categories (
  product_category_name TEXT PRIMARY KEY,
  product_category_name_english TEXT NOT NULL
);

CREATE TABLE products (
  product_id TEXT PRIMARY KEY,
  product_category_name TEXT REFERENCES product_categories,
  product_name_length INTEGER,
  product_description_length INTEGER,
  product_photos_qty INTEGER,
  product_weight_g INTEGER,
  product_length_cm INTEGER,
  product_height_cm INTEGER,
  product_width_cm INTEGER
);

CREATE TABLE orders (
  order_id TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers,
  order_status TEXT NOT NULL,
  order_purchase_timestamp TIMESTAMP NOT NULL,
  order_approved_at TIMESTAMP,
  order_delivered_carrier_date TIMESTAMP,
  order_delivered_customer_date TIMESTAMP,
  order_estimated_delivery_date TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
  order_id TEXT NOT NULL REFERENCES orders,
  order_item_id INTEGER NOT NULL,
  product_id TEXT NOT NULL REFERENCES products,
  seller_id TEXT NOT NULL REFERENCES sellers,
  shipping_limit_date TIMESTAMP NOT NULL,
  price NUMERIC(10, 2) NOT NULL,
  freight_value NUMERIC(10, 2) NOT NULL,
  PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE order_payments (
  order_id TEXT NOT NULL REFERENCES orders,
  payment_sequential INTEGER NOT NULL,
  payment_type TEXT NOT NULL,
  payment_installments INTEGER NOT NULL,
  payment_value NUMERIC(10, 2) NOT NULL,
  PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE order_reviews (
  review_id TEXT NOT NULL,
  order_id TEXT NOT NULL REFERENCES orders,
  review_score INTEGER NOT NULL CHECK (review_score BETWEEN 1 AND 5),
  review_comment_title TEXT,
  review_comment_message TEXT,
  review_creation_date TIMESTAMP NOT NULL,
  review_answer_timestamp TIMESTAMP NOT NULL,
  PRIMARY KEY (review_id, order_id)
);

CREATE TABLE geolocation (
  zip_code_prefix TEXT PRIMARY KEY,
  latitude DOUBLE PRECISION NOT NULL,
  longitude DOUBLE PRECISION NOT NULL,
  city TEXT NOT NULL,
  state TEXT NOT NULL
);

CREATE INDEX ON customers (customer_unique_id);
CREATE INDEX ON customers (customer_state);
CREATE INDEX ON products (product_category_name);
CREATE INDEX ON orders (customer_id);
CREATE INDEX ON orders (order_purchase_timestamp);
CREATE INDEX ON order_items (product_id);
CREATE INDEX ON order_items (seller_id);
CREATE INDEX ON order_reviews (order_id);

COMMENT ON TABLE customers IS
  'One row per order, not per person. Use customer_unique_id to count people.';
COMMENT ON COLUMN customers.customer_id IS
  'Unique to a single order. A repeat buyer has a new customer_id on each order.';
COMMENT ON COLUMN customers.customer_unique_id IS
  'Identifies the actual person across orders.';
COMMENT ON COLUMN customers.customer_zip_code_prefix IS
  'First five digits of the zip code, stored as text to keep leading zeros.';

COMMENT ON TABLE product_categories IS
  'Portuguese category names with English translations.';

COMMENT ON COLUMN products.product_category_name IS
  'Portuguese name. Join product_categories for English. NULL for some products.';

COMMENT ON COLUMN orders.order_status IS
  'Filter to delivered for completed sales. Others include shipped and canceled.';
COMMENT ON COLUMN orders.order_purchase_timestamp IS
  'When the customer placed the order. Use this for sales over time.';

COMMENT ON TABLE order_items IS
  'One row per item in an order. Sum price and freight_value for item revenue.';
COMMENT ON COLUMN order_items.order_item_id IS
  'Position of the item within the order, starting at 1. Not a global ID.';
COMMENT ON COLUMN order_items.price IS 'Item price in Brazilian reais (BRL).';
COMMENT ON COLUMN order_items.freight_value IS
  'Freight charged for this item in Brazilian reais (BRL).';

COMMENT ON TABLE order_payments IS
  'One row per payment. An order can have several, so joining it to order_items multiplies rows.';
COMMENT ON COLUMN order_payments.payment_value IS
  'Amount paid in Brazilian reais (BRL).';

COMMENT ON TABLE order_reviews IS
  'An order can have several reviews, and a review_id can cover several orders.';

COMMENT ON TABLE geolocation IS
  'One row per zip prefix, reduced from the raw data. Not every customer or seller prefix has a row.';
COMMENT ON COLUMN geolocation.latitude IS 'Median latitude of the raw points.';
COMMENT ON COLUMN geolocation.longitude IS 'Median longitude of the raw points.';
COMMENT ON COLUMN geolocation.city IS 'Most common spelling in the raw data.';
