#!/usr/bin/env bash
# Creates (or repairs) the PostgreSQL role and database named in .env.
# Run once from a normal terminal: bash scripts/setup_postgres.sh
# It needs sudo to act as the "postgres" admin user.
set -euo pipefail

cd "$(dirname "$0")/.."

read_env() { grep "^$1=" .env | cut -d= -f2-; }
DB_NAME=$(read_env DB_NAME)
DB_USER=$(read_env DB_USER)
DB_PASSWORD=$(read_env DB_PASSWORD)

if [ -z "$DB_NAME" ] || [ -z "$DB_USER" ] || [ -z "$DB_PASSWORD" ]; then
  echo "DB_NAME, DB_USER and DB_PASSWORD must be set in .env" >&2
  exit 1
fi

# Run from /tmp so the postgres user can enter the working directory.
cd /tmp
sudo -u postgres psql -v ON_ERROR_STOP=1 -v name="$DB_NAME" -v user="$DB_USER" -v pw="$DB_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN CREATEDB PASSWORD %L', :'user', :'pw')
  WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = :'user')\gexec
SELECT format('ALTER ROLE %I WITH LOGIN CREATEDB PASSWORD %L', :'user', :'pw')\gexec
SELECT format('CREATE DATABASE %I OWNER %I', :'name', :'user')
  WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = :'name')\gexec
SQL

echo "PostgreSQL is ready: database '$DB_NAME', user '$DB_USER'."
