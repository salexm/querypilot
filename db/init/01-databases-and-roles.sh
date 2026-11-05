#!/bin/sh
# Creates the databases and roles. Postgres runs this only when the data volume
# is empty, so changing these settings later needs `docker compose down -v`.
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname postgres \
  -v admin_user="$POSTGRES_USER" \
  -v analytics_db="$ANALYTICS_DB_NAME" \
  -v readonly_user="$ANALYTICS_READONLY_USER" \
  -v readonly_password="$ANALYTICS_READONLY_PASSWORD" \
  -v app_db="$APP_DB_NAME" \
  -v app_user="$APP_DB_USER" \
  -v app_password="$APP_DB_PASSWORD" \
  -v query_timeout_ms="$QUERY_TIMEOUT_MS" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'readonly_user', :'readonly_password') \gexec
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'app_user', :'app_password') \gexec

-- Defaults for generated SQL. The executor must still set its own limits.
SELECT format('ALTER ROLE %I SET default_transaction_read_only = on', :'readonly_user') \gexec
SELECT format('ALTER ROLE %I SET statement_timeout = %L', :'readonly_user', :'query_timeout_ms') \gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'analytics_db', :'admin_user') \gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'app_db', :'app_user') \gexec

-- PUBLIC can connect to every database by default, so each role is granted
-- only the database it needs.
REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'analytics_db') \gexec
SELECT format('REVOKE ALL ON DATABASE %I FROM PUBLIC', :'app_db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'analytics_db', :'readonly_user') \gexec

\connect :"analytics_db"

REVOKE ALL ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'readonly_user') \gexec

-- The seed drops and recreates tables, so SELECT must apply to future tables.
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT ON TABLES TO %I',
  :'admin_user',
  :'readonly_user'
) \gexec
SQL
