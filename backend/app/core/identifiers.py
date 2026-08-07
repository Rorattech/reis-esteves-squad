"""Emissão dos identificadores legíveis de caso e cliente (CAS-2026-000123, CLI-000042).

O UUID continua sendo a chave primária e o que aparece na URL — não é
enumerável, e é o que impede alguém de descobrir quantos casos o escritório
tem trocando um número. Mas UUID é ilegível para quem trabalha com o caso: o
advogado precisa de algo que caiba numa conversa ("o CAS-2026-000123"). Estas
duas identidades convivem de propósito.
"""

import enum
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: Fuso do escritório. O ano do código sai daqui, não de UTC: um caso aberto em
#: 31/dez às 21h em Brasília é de 1º de janeiro em UTC, e receberia o código do
#: ano seguinte — confusão gratuita num identificador que o advogado cita.
_OFFICE_TIMEZONE = ZoneInfo("America/Sao_Paulo")

#: Ano convencionado para escopos perenes, que não reiniciam a contagem.
_PERENNIAL_YEAR = 0


class CodeScope(enum.Enum):
    """Séries de identificadores emitidas por escritório.

    Cada membro carrega o prefixo, a largura do número e se a série reinicia a
    cada ano. Casos são datados por natureza (o ano ajuda a situar o caso na
    conversa); clientes são perenes — o mesmo cliente atravessa anos e trocar o
    código dele em 1º de janeiro não faria sentido.
    """

    CASE = ("case", "CAS", 6, True)
    CLIENT = ("client", "CLI", 6, False)

    def __init__(self, scope: str, prefix: str, width: int, yearly: bool) -> None:
        self.scope = scope
        self.prefix = prefix
        self.width = width
        self.yearly = yearly


# ON CONFLICT DO UPDATE em vez de SELECT ... FOR UPDATE seguido de UPDATE: uma
# única instrução, então o row lock do UPDATE serializa duas requests
# simultâneas do mesmo tenant sem transação explícita nem risco de deadlock.
# COALESCE cobre a primeira emissão da série, quando ainda não há linha.
_ALLOCATE_NEXT = text("""
    INSERT INTO tenant_counters (tenant_id, scope, year, last_value)
    VALUES (:tenant_id, :scope, :year, 1)
    ON CONFLICT (tenant_id, scope, year)
    DO UPDATE SET last_value = tenant_counters.last_value + 1
    RETURNING last_value
    """)


def format_code(scope: CodeScope, *, year: int, value: int) -> str:
    """Monta o código legível a partir do número emitido.

    Args:
        scope: Série do identificador.
        year: Ano da série (ignorado em séries perenes).
        value: Número sequencial emitido para o tenant.

    Returns:
        O código formatado (ex.: "CAS-2026-000123" ou "CLI-000042").
    """
    number = str(value).zfill(scope.width)
    return f"{scope.prefix}-{year}-{number}" if scope.yearly else f"{scope.prefix}-{number}"


def current_year() -> int:
    """Retorna o ano corrente no fuso do escritório.

    Returns:
        Ano com quatro dígitos em America/Sao_Paulo.
    """
    return datetime.now(_OFFICE_TIMEZONE).year


async def next_code(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    scope: CodeScope,
) -> str:
    """Emite o próximo código legível de uma série, para um escritório.

    A emissão participa da transação corrente: se o caso que motivou a chamada
    falhar, o número volta atrás junto. Buracos ainda são possíveis (um commit
    parcial seguido de erro adiante), e são aceitáveis — o código identifica,
    não conta.

    Args:
        session: Sessão do banco já escopada por tenant.
        tenant_id: Tenant autenticado da request — nunca vindo do payload.
        scope: Série a emitir (caso ou cliente).

    Returns:
        O próximo código formatado da série para este tenant.
    """
    year = current_year() if scope.yearly else _PERENNIAL_YEAR
    value = await session.scalar(
        _ALLOCATE_NEXT,
        {"tenant_id": tenant_id, "scope": scope.scope, "year": year},
    )
    return format_code(scope, year=year, value=int(value))
