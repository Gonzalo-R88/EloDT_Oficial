"""Caché en disco del crudo parseado (resume/reanudable)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class RawStore:
    """Almacén de datos crudos por competencia/temporada.

    Estructura:
        data/raw/{competition}/{season}/fixtures.json
        data/raw/{competition}/{season}/matches/{match_id}.json
    """

    def __init__(self, base_dir: Path) -> None:
        self.base = Path(base_dir) / "raw"

    def season_dir(self, competition_code: str, season: int) -> Path:
        return self.base / competition_code / str(season)

    def fixtures_path(self, competition_code: str, season: int) -> Path:
        return self.season_dir(competition_code, season) / "fixtures.json"

    def match_path(self, competition_code: str, season: int, match_id: int) -> Path:
        return self.season_dir(competition_code, season) / "matches" / f"{match_id}.json"

    # -- fixtures -----------------------------------------------------------
    def has_fixtures(self, competition_code: str, season: int) -> bool:
        return self.fixtures_path(competition_code, season).exists()

    def read_fixtures(self, competition_code: str, season: int) -> list[dict[str, Any]]:
        return self._read_json(self.fixtures_path(competition_code, season))

    def write_fixtures(self, competition_code: str, season: int, data: list[dict[str, Any]]) -> None:
        self._write_json(self.fixtures_path(competition_code, season), data)

    # -- matches ------------------------------------------------------------
    def has_match(self, competition_code: str, season: int, match_id: int) -> bool:
        return self.match_path(competition_code, season, match_id).exists()

    def read_match(self, competition_code: str, season: int, match_id: int) -> dict[str, Any]:
        return self._read_json(self.match_path(competition_code, season, match_id))

    def write_match(self, competition_code: str, season: int, match_id: int, data: dict[str, Any]) -> None:
        self._write_json(self.match_path(competition_code, season, match_id), data)

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _read_json(path: Path) -> Any:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    @staticmethod
    def _write_json(path: Path, data: Any) -> None:
        """Escritura atómica: escribe a un temporal y luego renombra.

        Evita dejar archivos JSON corruptos si el proceso se interrumpe a mitad
        de la escritura, garantizando que la caché siempre sea reanudable.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(tmp_name, path)
        except BaseException:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
            raise
