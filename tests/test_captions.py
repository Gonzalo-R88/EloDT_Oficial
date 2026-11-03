"""Tests de los textos sugeridos (`captions.py`)."""

from dataclasses import dataclass

import pytest

from captions import LIMITE_X, Textos, textos_top10


@dataclass(frozen=True)
class _Entrada:
    dt: str
    elo: float
    puesto: int


@dataclass(frozen=True)
class _Movimiento:
    dt: str
    delta: float


def _entradas():
    return [
        _Entrada("Rodolfo Arruabarrena", 1206.7, 1),
        _Entrada("Jorge Almirón", 1160.3, 2),
        _Entrada("Guillermo Barros Schelotto", 1150.5, 3),
        _Entrada("Alfredo Berti", 1140.6, 4),
    ]


def test_genera_los_cuatro_textos():
    textos = textos_top10(_entradas(), "semana del 26/10 al 1/11")

    assert isinstance(textos, Textos)
    assert textos.linkedin and textos.x and textos.instagram and textos.alt


def test_los_textos_incluyen_los_datos_reales():
    textos = textos_top10(_entradas(), "semana del 26/10 al 1/11", partidos=42)

    assert "Arruabarrena" in textos.linkedin
    assert "1207" in textos.linkedin  # ELO redondeado
    assert "42 partidos" in textos.linkedin
    assert "Arruabarrena" in textos.x
    assert "1207" in textos.instagram


def test_x_no_supera_el_limite_aunque_el_texto_sea_largo():
    entradas = [
        _Entrada("Guillermo Martín Barros Schelotto Fernández", 9999.0, 1),
        _Entrada("Mauricio Pellegrino y Asociados", 8888.0, 2),
        _Entrada("Ricardo Zielinski", 7777.0, 3),
    ]

    textos = textos_top10(entradas, "semana del 26 de octubre al 1 de noviembre de 2026")

    assert len(textos.x) <= LIMITE_X


def test_avisa_si_no_hay_entradas():
    with pytest.raises(ValueError):
        textos_top10([], "semana")


def test_el_alt_describe_la_imagen():
    textos = textos_top10(_entradas(), "semana del 26/10 al 1/11")

    assert "Arruabarrena" in textos.alt
    assert "1207" in textos.alt


def test_los_textos_mencionan_la_fuente_de_los_datos():
    textos = textos_top10(_entradas(), "semana del 26/10 al 1/11")

    assert "Transfermarkt" in textos.linkedin
    assert "ELO propio" in textos.linkedin
