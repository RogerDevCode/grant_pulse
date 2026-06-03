"""Tests para el parser de fechas chilenas."""

from datetime import UTC, datetime

from src.core.domain.fecha_utils import parse_fecha_chilena


def test_formato_dia_de_mes_de_anio() -> None:
    assert parse_fecha_chilena("15 de agosto de 2026") == datetime(2026, 8, 15, tzinfo=UTC)


def test_formato_dia_de_mes_abrev_de_anio() -> None:
    assert parse_fecha_chilena("15 de ago de 2026") == datetime(2026, 8, 15, tzinfo=UTC)


def test_formato_slash() -> None:
    assert parse_fecha_chilena("15/08/2026") == datetime(2026, 8, 15, tzinfo=UTC)


def test_formato_dash() -> None:
    assert parse_fecha_chilena("15-08-2026") == datetime(2026, 8, 15, tzinfo=UTC)


def test_formato_iso() -> None:
    assert parse_fecha_chilena("2026-08-15") == datetime(2026, 8, 15, tzinfo=UTC)


def test_fecha_con_texto_alrededor() -> None:
    result = parse_fecha_chilena("Postulaciones hasta el 15 de agosto de 2026")
    assert result == datetime(2026, 8, 15, tzinfo=UTC)


def test_fecha_vacia_retorna_none() -> None:
    assert parse_fecha_chilena("") is None


def test_fecha_none_retorna_none() -> None:
    assert parse_fecha_chilena("") is None


def test_fecha_invalida_retorna_none() -> None:
    assert parse_fecha_chilena("no es una fecha") is None


def test_fecha_dia_invalido_retorna_none() -> None:
    assert parse_fecha_chilena("32 de enero de 2026") is None


def test_mes_invalido_retorna_none() -> None:
    assert parse_fecha_chilena("15 de xyz de 2026") is None
