"""Pruebas de descarga (sin red), lectura de páginas y base SQLite."""
import io
import urllib.error
from pathlib import Path

import pytest

from conftest import cargar_referencia, cargar_textos
from vigia import base, descargar, leer, validar


# --- Descarga -----------------------------------------------------------------------

def test_ediciones_y_url():
    lista = descargar.ediciones()
    assert lista[0] == "202510" and lista[-1] == "202609" and len(lista) == 12
    assert descargar.url_de("202609") == \
        "https://www.cne.cl/wp-content/uploads/2026/09/RMensual_ERNC_v202609.pdf"


def test_es_pdf():
    assert descargar.es_pdf(b"%PDF-1.7 ...")
    assert not descargar.es_pdf(b"<!DOCTYPE html><html>No encontrado")


def test_mayo_2026_queda_faltante_sin_detener_el_resto(tmp_path, monkeypatch):
    """Simula la CNE: mayo responde 404, abril una página HTML y junio un PDF."""
    def urlopen_simulado(pedido, timeout):
        url = pedido.full_url
        if "202605" in url:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        if "202604" in url:
            return io.BytesIO(b"<html>error</html>")
        return io.BytesIO(b"%PDF-1.7 contenido")

    monkeypatch.setattr(descargar.urllib.request, "urlopen", urlopen_simulado)
    registros = [descargar.descargar_edicion(e, tmp_path) for e in ("202604", "202605", "202606")]

    assert [r["estado"] for r in registros] == ["faltante", "faltante", "ok"]
    assert registros[2]["sha256"] and len(registros[2]["sha256"]) == 64
    assert sorted(p.name for p in tmp_path.iterdir()) == ["202606.pdf"]


# --- Lectura ------------------------------------------------------------------------

def test_etapa_de_pagina():
    textos = cargar_textos("202609")
    assert leer.etapa_de_pagina(textos["ingreso"]) == "ingreso"
    assert leer.etapa_de_pagina(textos["aprobacion"]) == "aprobacion"
    # el índice nombra las secciones pero no trae la tabla
    assert leer.etapa_de_pagina("1. Proyectos Ingresados a Evaluación Ambiental\n3. Proyectos con RCA Aprobada") is None


PDF = Path("datos/reportes")


@pytest.mark.skipif(not (PDF / "202609.pdf").exists(), reason="PDF no descargado")
def test_paginas_cambian_entre_ediciones():
    assert {k: v["pagina"] for k, v in leer.leer_tablas(PDF / "202609.pdf").items()} == \
        {"ingreso": 6, "aprobacion": 7}
    if (PDF / "202510.pdf").exists():
        assert {k: v["pagina"] for k, v in leer.leer_tablas(PDF / "202510.pdf").items()} == \
            {"ingreso": 7, "aprobacion": 8}


# --- Base ---------------------------------------------------------------------------

def test_base_guarda_y_agrupa_proyectos():
    con = base.conectar(":memory:")
    base.guardar_reportes(con, [
        {"edicion": "202609", "url": "u", "sha256": "x", "descargado": "hoy", "estado": "ok"},
        {"edicion": "202605", "url": "u", "sha256": None, "descargado": None, "estado": "faltante"}])
    ref, textos = cargar_referencia("202609"), cargar_textos("202609")
    paginas = {"ingreso": {"pagina": 6, "texto": textos["ingreso"]},
               "aprobacion": {"pagina": 7, "texto": textos["aprobacion"]}}
    controles = validar.validar_edicion("202609", ref, textos)
    base.guardar_edicion(con, "202609", paginas, ref["filas"], controles)
    base.guardar_edicion(con, "202609", paginas, ref["filas"], controles)  # repetir no duplica

    assert con.execute("SELECT COUNT(*) FROM filas").fetchone()[0] == 12
    assert con.execute("SELECT COUNT(*) FROM controles").fetchone()[0] == 14
    assert con.execute("SELECT estado FROM reportes WHERE edicion = '202605'").fetchone()[0] == "faltante"
    el_faro = con.execute("SELECT potencia_mw, pagina FROM filas WHERE nombre LIKE '%El Faro%'").fetchone()
    assert el_faro["potencia_mw"] is None and el_faro["pagina"] == 6
    # CIUDADLUZ tiene dos proyectos distintos: la vista no los mezcla
    assert con.execute("SELECT COUNT(*) FROM proyectos WHERE titular = 'CIUDADLUZ'").fetchone()[0] == 2
    assert len(base.filas_previas(con, "202610")) == 12
