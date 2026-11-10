"""Tests de los textos sugeridos (`captions.py`).

Regla de la casa: el texto sale para X (≤280) y se usa igual en LinkedIn. Sin hashtags,
sin nombrar la fuente de los datos y sin el handle, que va sólo en la imagen.
"""

from dataclasses import dataclass
from datetime import date
from types import SimpleNamespace

import pytest

from captions import (
    LIMITE_POST,
    Textos,
    textos_duelo,
    textos_movimientos,
    textos_revelacion,
    textos_top10,
)

SEMANA = "del 26 de octubre al 1 de noviembre"


@dataclass(frozen=True)
class _Entrada:
    dt: str
    elo: float
    puesto: int = 1


@dataclass(frozen=True)
class _Movimiento:
    dt: str
    delta: float


@dataclass(frozen=True)
class _Lado:
    nombre: str
    club: str


@dataclass(frozen=True)
class _Duelo:
    """Igual que `content.DueloSemana`: los nombres están en el Duel interno."""

    club_a: str
    club_b: str
    duelo: object

    @property
    def elo_combinado(self) -> float:
        return 2057.0


@dataclass(frozen=True)
class _Revelacion:
    dt: str
    club: str
    elo: float
    pj: int
    variacion: float
    desde_primera_fecha: date


def _entradas():
    return [
        _Entrada("Rodolfo Arruabarrena", 1206.7, 1),
        _Entrada("Jorge Almirón", 1160.3, 2),
        _Entrada("Guillermo Barros Schelotto", 1150.5, 3),
        _Entrada("Alfredo Berti", 1140.6, 4),
    ]


def _textos_de_ejemplo() -> dict[str, Textos]:
    """Un texto de cada formato, para las reglas que valen para todos."""
    return {
        "top10": textos_top10(_entradas(), SEMANA, pais="Argentina"),
        "movers": textos_movimientos(
            [_Movimiento("Federico Medina", 14.2)],
            [_Movimiento("Marcelo Gallardo", -11.8)],
            SEMANA,
        ),
        "duelo": textos_duelo(
            _Duelo(
                "Chaco For Ever", "Instituto",
                SimpleNamespace(
                    a=_Lado("Walter Marchetti", "Chaco For Ever"),
                    b=_Lado("Sebastián Domínguez", "Instituto"),
                ),
            ),
            SEMANA,
        ),
        "revelacion": textos_revelacion(
            _Revelacion("Federico Medina", "Independiente", 1234.4, 28, 12.5,
                        date(2025, 3, 12)),
            SEMANA,
        ),
    }


def test_cada_formato_tiene_texto_y_alt():
    for formato, textos in _textos_de_ejemplo().items():
        assert isinstance(textos, Textos), formato
        assert textos.texto.strip(), formato
        assert textos.alt.strip(), formato


def test_el_texto_incluye_los_datos_reales():
    textos = textos_top10(_entradas(), SEMANA, pais="Argentina")

    assert "Top 10 DTs de Argentina" in textos.texto
    assert "1. Arruabarrena 1207" in textos.texto  # apellido + ELO redondeado
    assert "2. Almirón 1160" in textos.texto
    assert "3. Schelotto 1150" in textos.texto  # round() de 1150.5 es par


def test_el_top_global_no_dice_argentina():
    """El ranking mundial se armaba con el título de Argentina (bug)."""
    textos = textos_top10(_entradas(), SEMANA, pais=None)

    assert "Top 10 DTs del mundo" in textos.texto
    assert "Argentina" not in textos.texto


def test_ningun_texto_supera_el_limite_de_x():
    for formato, textos in _textos_de_ejemplo().items():
        assert len(textos.texto) <= LIMITE_POST, formato


def test_el_limite_recorta_textos_larguisimos():
    semana_larga = (
        "del 26 de octubre al 1 de noviembre de 2026, con las fechas completas del "
        "calendario y el detalle de toda la ventana considerada para el cálculo"
    )

    textos = textos_top10(_entradas(), semana_larga, pais="Argentina")

    assert len(textos.texto) <= LIMITE_POST
    assert textos.texto.endswith("…")


def test_los_textos_no_nombran_la_fuente_ni_el_handle():
    for formato, textos in _textos_de_ejemplo().items():
        assert "Transfermarkt" not in textos.texto, formato
        assert "@" not in textos.texto, formato


def test_los_textos_no_llevan_hashtags():
    for formato, textos in _textos_de_ejemplo().items():
        assert "#" not in textos.texto, formato


def test_avisa_si_no_hay_entradas():
    with pytest.raises(ValueError):
        textos_top10([], SEMANA)


def test_avisa_si_no_hay_movimientos():
    with pytest.raises(ValueError):
        textos_movimientos([], [], SEMANA)


def test_el_alt_describe_la_imagen():
    textos = textos_top10(_entradas(), SEMANA, pais="Argentina")

    assert "Arruabarrena" in textos.alt
    assert "1207" in textos.alt
    assert "segundo Jorge Almirón" in textos.alt


def test_el_duelo_nombra_a_los_dos_dts():
    """El texto salía con 'DT A () vs DT B ()': leía campos que no existen."""
    textos = _textos_de_ejemplo()["duelo"]

    assert "Walter Marchetti (Chaco For Ever) vs Sebastián Domínguez (Instituto)" in textos.texto
    assert "DT A" not in textos.texto


def test_los_decimales_van_con_coma():
    """El proyecto escribe en español: +14,2 y no +14.2."""
    revelacion = _textos_de_ejemplo()["revelacion"]

    assert "+12,5 en los últimos 90 días." in revelacion.texto
    assert "días," not in revelacion.texto  # el reemplazo no toca la puntuación


def test_movimientos_describe_quien_subio_y_quien_bajo():
    textos = textos_movimientos(
        [_Movimiento("Federico Medina", 14.2)],
        [_Movimiento("Marcelo Gallardo", -11.8)],
        SEMANA,
    )

    assert "Subió más: Federico Medina (+14,2)" in textos.texto
    assert "Bajó más: Marcelo Gallardo (-11,8)" in textos.texto
