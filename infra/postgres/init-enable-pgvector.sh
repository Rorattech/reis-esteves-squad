#!/bin/bash
# Roda na primeira inicialização do volume (docker-entrypoint-initdb.d), como o
# superusuário de bootstrap do initdb (POSTGRES_USER/POSTGRES_PASSWORD — ver
# docker-compose.yml e init-app-role.sh).
#
# CREATE EXTENSION exige privilégio de superusuário nesta imagem/versão do
# pgvector (0.8.5) — DB_USER (dono do banco, mas sem SUPERUSER por design, ver
# init-app-role.sh) não tem essa permissão. Por isso a extensão é habilitada
# aqui, fora do Alembic: toda migration roda com as credenciais de DB_USER via
# DATABASE_URL, e um `CREATE EXTENSION` nela falharia com
# "permission denied to create extension" (docs/architecture.md, seção 3.5).
#
# Nenhuma tabela/coluna vetorial é criada aqui — isso é responsabilidade do
# Módulo 3 (Research/RAG) quando for implementado; este passo só remove o
# bloqueio de infraestrutura.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE EXTENSION IF NOT EXISTS vector;
EOSQL
