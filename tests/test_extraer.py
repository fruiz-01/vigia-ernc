"""Pruebas de la extracción con un cliente simulado: sin red y sin clave."""
import copy
import json
from types import SimpleNamespace

import pytest

from conftest import cargar_referencia, cargar_textos
from vigia import extraer
from vigia.extraer import Extraccion


class ClienteSimulado:
    """Imita a anthropic.Anthropic(): entrega respuestas preparadas y anota cada llamada."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.messages = self  # cliente.messages.parse(...)

    def parse(self, **kwargs):
        self.llamadas.append(kwargs)
        return self.respuestas.pop(0)


def respuesta(datos, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason, parsed_output=Extraccion.model_validate(datos))


@pytest.fixture
def paginas():
    textos = cargar_textos("202609")
    return {"ingreso": {"pagina": 6, "texto": textos["ingreso"]},
            "aprobacion": {"pagina": 7, "texto": textos["aprobacion"]}}


def test_extrae_y_guarda_cache(tmp_path, paginas):
    ref = cargar_referencia("202609")
    cliente = ClienteSimulado(respuesta(ref))
    resultado = extraer.extraer_edicion("202609", paginas, cliente, carpeta=tmp_path)

    assert len(cliente.llamadas) == 1
    llamada = cliente.llamadas[0]
    assert llamada["model"] == "claude-opus-5-5"
    assert llamada["output_format"] is Extraccion
    assert llamada["output_config"] == {"effort": "low"}
    assert "Parque Eólico Viena" in llamada["messages"][0]["content"]  # el texto de la página va en el mensaje

    assert len(resultado["intentos"]) == 1
    assert resultado["intentos"][0]["filas"][0]["fecha"] == "2026-08-19"
    assert (tmp_path / "202609.json").exists()

    # con la caché no se vuelve a llamar al modelo
    otro = ClienteSimulado()
    assert extraer.extraer_edicion("202609", paginas, otro, carpeta=tmp_path) == json.loads(
        (tmp_path / "202609.json").read_text(encoding="utf-8"))
    assert otro.llamadas == []


def test_reintenta_una_vez_con_la_diferencia(tmp_path, paginas):
    ref = cargar_referencia("202609")
    incompleta = copy.deepcopy(ref)
    # el modelo se salta Las Mellizas (212 MW, 400 MMUSD)
    incompleta["filas"] = [f for f in ref["filas"] if f["nombre"] != "Planta Fotovoltaica Las Mellizas"]
    cliente = ClienteSimulado(respuesta(incompleta), respuesta(ref))

    resultado = extraer.extraer_edicion("202609", paginas, cliente, carpeta=tmp_path)

    assert len(cliente.llamadas) == 2
    reclamo = cliente.llamadas[1]["messages"][-1]["content"]
    assert "las filas suman 309 MW y el reporte declara 521" in reclamo
    assert "hay 7 filas y el reporte declara 8" in reclamo
    assert len(resultado["intentos"]) == 2
    assert len(resultado["intentos"][-1]["filas"]) == 12


def test_no_reintenta_mas_de_una_vez(tmp_path, paginas):
    ref = cargar_referencia("202609")
    mala = copy.deepcopy(ref)
    mala["filas"] = mala["filas"][:-1]
    cliente = ClienteSimulado(respuesta(mala), respuesta(mala))
    resultado = extraer.extraer_edicion("202609", paginas, cliente, carpeta=tmp_path)
    assert len(cliente.llamadas) == 2  # el error queda para revisión manual
    assert len(resultado["intentos"]) == 2


@pytest.mark.parametrize("motivo", ["refusal", "max_tokens"])
def test_stop_reason_malo_es_error(tmp_path, paginas, motivo):
    cliente = ClienteSimulado(respuesta(cargar_referencia("202609"), stop_reason=motivo))
    with pytest.raises(RuntimeError, match=motivo):
        extraer.extraer_edicion("202609", paginas, cliente, carpeta=tmp_path)
    assert not (tmp_path / "202609.json").exists()  # nada a medias en la caché
