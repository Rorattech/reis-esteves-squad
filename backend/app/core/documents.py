"""Validação e normalização de documentos brasileiros (CPF, CNPJ, CEP).

Toda escrita no banco guarda **apenas os dígitos**: o advogado digita
"529.982.247-25" ou "52998224725" conforme o humor, e sem normalizar na
entrada a checagem de duplicidade por documento
(uq_clients_tenant_id_document_number) deixaria os dois passarem como clientes
diferentes. A formatação com máscara é responsabilidade da interface
(frontend/src/lib/documents.ts).

Segurança: estas funções apenas validam formato e dígito verificador. Um CPF
estruturalmente válido não é prova de identidade e **nunca** deve ser tratado
como credencial de acesso — ver a docstring de app/models/client.py.
"""

import re

_NON_DIGITS = re.compile(r"\D")

CPF_LENGTH = 11
CNPJ_LENGTH = 14
ZIP_CODE_LENGTH = 8

#: Pesos do primeiro e do segundo dígito verificador do CNPJ. O CPF usa uma
#: progressão simples (10..2 e 11..2), calculada direto na função.
_CNPJ_FIRST_WEIGHTS = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_CNPJ_SECOND_WEIGHTS = (6, *_CNPJ_FIRST_WEIGHTS)


def strip_non_digits(value: str) -> str:
    """Remove tudo que não for dígito de um texto.

    Args:
        value: Texto possivelmente formatado com máscara.

    Returns:
        Somente os dígitos, na ordem original.
    """
    return _NON_DIGITS.sub("", value)


def _check_digit(digits: str, weights: tuple[int, ...]) -> int:
    """Calcula um dígito verificador pelo módulo 11 usado em CPF e CNPJ.

    Args:
        digits: Dígitos base sobre os quais o verificador é calculado.
        weights: Pesos aplicados a cada dígito, na mesma ordem.

    Returns:
        O dígito verificador (0 quando o resto do módulo 11 é menor que 2).
    """
    total = sum(int(digit) * weight for digit, weight in zip(digits, weights))
    remainder = total % 11
    return 0 if remainder < 2 else 11 - remainder


def is_valid_cpf(value: str) -> bool:
    """Verifica se um CPF é estruturalmente válido (11 dígitos + verificadores).

    Args:
        value: CPF com ou sem máscara.

    Returns:
        True se o CPF tiver 11 dígitos, não for uma sequência de dígitos iguais
        e os dois dígitos verificadores conferirem.
    """
    digits = strip_non_digits(value)
    if len(digits) != CPF_LENGTH or len(set(digits)) == 1:
        # "111.111.111-11" e afins passam no módulo 11 mas não são CPFs reais.
        return False

    first = _check_digit(digits[:9], tuple(range(10, 1, -1)))
    second = _check_digit(digits[:10], tuple(range(11, 1, -1)))
    return digits[9:] == f"{first}{second}"


def is_valid_cnpj(value: str) -> bool:
    """Verifica se um CNPJ é estruturalmente válido (14 dígitos + verificadores).

    Args:
        value: CNPJ com ou sem máscara.

    Returns:
        True se o CNPJ tiver 14 dígitos, não for uma sequência de dígitos
        iguais e os dois dígitos verificadores conferirem.
    """
    digits = strip_non_digits(value)
    if len(digits) != CNPJ_LENGTH or len(set(digits)) == 1:
        return False

    first = _check_digit(digits[:12], _CNPJ_FIRST_WEIGHTS)
    second = _check_digit(digits[:13], _CNPJ_SECOND_WEIGHTS)
    return digits[12:] == f"{first}{second}"


def normalize_zip_code(value: str) -> str | None:
    """Normaliza um CEP para 8 dígitos.

    Args:
        value: CEP com ou sem máscara (ex.: "01310-100").

    Returns:
        Os 8 dígitos do CEP, ou None se o valor não tiver exatamente 8 dígitos.
    """
    digits = strip_non_digits(value)
    return digits if len(digits) == ZIP_CODE_LENGTH else None
