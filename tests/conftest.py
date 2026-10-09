"""Datos compartidos por las pruebas: textos de página y referencias transcritas a mano."""
import json
from pathlib import Path

import pytest

DATOS = Path(__file__).parent / "datos"


def cargar_referencia(edicion):
    return json.loads((DATOS / f"esperado_{edicion}.json").read_text(encoding="utf-8"))


def cargar_textos(edicion):
    return {etapa: (DATOS / f"texto_{edicion}_{etapa}.txt").read_text(encoding="utf-8")
            for etapa in ("ingreso", "aprobacion")}


@pytest.fixture
def ref_202609():
    return cargar_referencia("202609")


@pytest.fixture
def textos_202609():
    return cargar_textos("202609")
