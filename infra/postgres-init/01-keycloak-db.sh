#!/bin/bash
# Creates the Keycloak database alongside the application one.
#
# Keycloak manages its own schema and migrates it on every version bump. Giving
# it a separate database keeps that churn out of the application's search_path
# and makes `pg_dump ntt` a clean application-only backup.
#
# Runs only on first initialisation of an empty data directory (Postgres image
# convention). On an existing volume this file is ignored, hence IF NOT EXISTS
# semantics via the SELECT-then-create guard below.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    SELECT 'CREATE DATABASE keycloak'
    WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec

    GRANT ALL PRIVILEGES ON DATABASE keycloak TO "$POSTGRES_USER";
EOSQL

echo "keycloak database ready"
