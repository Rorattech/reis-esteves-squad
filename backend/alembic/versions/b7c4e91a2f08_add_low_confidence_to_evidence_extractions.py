"""add low_confidence flag to evidence_extractions

Revision ID: b7c4e91a2f08
Revises: 8b41c72fd9ae
Create Date: 2026-08-17 09:41:20.118377

Fase 3.2 (revisão do OCR) — o pipeline passa a gravar explicitamente quando a
leitura automática ficou abaixo do patamar de confiança aceitável, em vez de
deixar a interface derivar isso na hora de exibir.

O veredito é gravado na linha imutável de `evidence_extractions` porque o
patamar (`extraction_low_confidence_threshold`) é configuração: mudá-lo depois
não pode reescrever retroativamente o julgamento de execuções passadas, que já
podem ter sido conferidas e citadas por um advogado.

`server_default="false"` cobre as linhas históricas (extrações do tesseract
local, kind "image_ocr"/"pdf_ocr"): elas não foram avaliadas contra patamar
nenhum, e marcá-las como insuficientes criaria uma fila de conferência falsa.
Não há mudança de RLS — a policy de tenant_isolation da tabela já vale para a
coluna nova.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b7c4e91a2f08"
down_revision: Union[str, Sequence[str], None] = "8b41c72fd9ae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "evidence_extractions",
        sa.Column(
            "low_confidence",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("evidence_extractions", "low_confidence")
