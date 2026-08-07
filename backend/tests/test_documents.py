"""Testes de validação e normalização de documentos brasileiros (app/core/documents.py)."""

import pytest

from app.core.documents import (
    is_valid_cnpj,
    is_valid_cpf,
    normalize_zip_code,
    strip_non_digits,
)


@pytest.mark.parametrize(
    "value",
    [
        "529.982.247-25",
        "52998224725",
        "  529 982 247 25  ",
        "168.995.350-09",
    ],
)
def test_valid_cpf_is_accepted_with_or_without_mask(value: str) -> None:
    assert is_valid_cpf(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "529.982.247-24",  # segundo dígito verificador errado
        "529.982.247-15",  # primeiro dígito verificador errado
        "111.111.111-11",  # sequência repetida passa no módulo 11, mas não é CPF
        "000.000.000-00",
        "5299822472",  # 10 dígitos
        "529982247250",  # 12 dígitos
        "",
        "abc.def.ghi-jk",
    ],
)
def test_invalid_cpf_is_rejected(value: str) -> None:
    assert is_valid_cpf(value) is False


@pytest.mark.parametrize(
    "value",
    [
        "11.222.333/0001-81",
        "11222333000181",
        "34.028.316/0001-03",
    ],
)
def test_valid_cnpj_is_accepted_with_or_without_mask(value: str) -> None:
    assert is_valid_cnpj(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "11.222.333/0001-82",  # dígito verificador errado
        "11.111.111/1111-11",  # sequência repetida
        "1122233300018",  # 13 dígitos
        "",
    ],
)
def test_invalid_cnpj_is_rejected(value: str) -> None:
    assert is_valid_cnpj(value) is False


def test_cpf_and_cnpj_do_not_validate_each_other() -> None:
    """Um CPF válido não pode passar como CNPJ e vice-versa — é o que sustenta
    a checagem de natureza PF/PJ em client_service."""
    assert is_valid_cnpj("529.982.247-25") is False
    assert is_valid_cpf("11.222.333/0001-81") is False


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("01310-100", "01310100"),
        ("01310100", "01310100"),
        ("1310-100", None),  # 7 dígitos
        ("013101000", None),  # 9 dígitos
        ("", None),
    ],
)
def test_normalize_zip_code(value: str, expected: str | None) -> None:
    assert normalize_zip_code(value) == expected


def test_strip_non_digits_preserves_order() -> None:
    assert strip_non_digits("(11) 98765-4321") == "11987654321"
