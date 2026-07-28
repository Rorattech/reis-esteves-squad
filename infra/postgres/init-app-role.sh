#!/bin/bash
# Roda primeiro (ordem alfabética) na primeira inicialização do volume.
#
# POSTGRES_USER/POSTGRES_PASSWORD (ver docker-compose.yml) são o superusuário
# de bootstrap do initdb — usado só internamente pelo container Postgres,
# nunca pela aplicação. O Postgres proíbe remover SUPERUSER desse usuário
# (DETAIL: "The bootstrap user must have the SUPERUSER attribute"), e
# superusers sempre ignoram Row Level Security mesmo com FORCE ROW LEVEL
# SECURITY (CLAUDE.md, seção 7) — então a aplicação precisa de um segundo
# usuário, sem SUPERUSER, dono do banco.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE "${DB_USER}" WITH LOGIN PASSWORD '${DB_PASSWORD}';
    ALTER DATABASE "${POSTGRES_DB}" OWNER TO "${DB_USER}";
EOSQL
