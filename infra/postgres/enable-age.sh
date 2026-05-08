#!/bin/bash
set -e

# Enable AGE extension on the default database. Block B will create the actual
# graph(s) per tenant.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS age;
EOSQL
