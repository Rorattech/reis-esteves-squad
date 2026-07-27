#!/bin/bash
# Executado automaticamente pela imagem oficial do Postgres na primeira inicialização
# (docker-entrypoint-initdb.d), apenas quando o volume de dados está vazio.
# Cria o banco/usuário dedicado do n8n, isolado do banco da aplicação.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE USER "${N8N_DB_USER}" WITH PASSWORD '${N8N_DB_PASSWORD}';
    CREATE DATABASE "${N8N_DB_NAME}" OWNER "${N8N_DB_USER}";
    GRANT ALL PRIVILEGES ON DATABASE "${N8N_DB_NAME}" TO "${N8N_DB_USER}";
EOSQL
