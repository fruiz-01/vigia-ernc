"""Descarga los reportes mensuales ERNC de la CNE.

Cada edición se guarda como datos/reportes/AAAAMM.pdf junto con su huella SHA-256.
Si una edición no existe (o la CNE responde con una página HTML), queda como «faltante»
y se sigue con la siguiente: un mes caído no detiene la corrida.
"""
import hashlib
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

CARPETA = Path("datos/reportes")
URL = "https://www.cne.cl/wp-content/uploads/{a}/{m}/RMensual_ERNC_v{a}{m}.pdf"


def ediciones(desde="202510", hasta="202609"):
    """Lista de ediciones 'AAAAMM' entre dos meses, ambos incluidos."""
    a, m = int(desde[:4]), int(desde[4:])
    lista = []
    while f"{a}{m:02d}" <= hasta:
        lista.append(f"{a}{m:02d}")
        a, m = (a + 1, 1) if m == 12 else (a, m + 1)
    return lista


def url_de(edicion):
    return URL.format(a=edicion[:4], m=edicion[4:])


def es_pdf(contenido):
    """Un PDF real parte con '%PDF'; una página de error parte con '<!DOCTYPE' o '<html'."""
    return contenido[:5] == b"%PDF-"


def descargar_edicion(edicion, carpeta=CARPETA):
    """Descarga una edición y devuelve el registro para la tabla `reportes`."""
    url = url_de(edicion)
    registro = {"edicion": edicion, "url": url, "sha256": None,
                "descargado": None, "estado": "faltante"}
    ruta = carpeta / f"{edicion}.pdf"

    if ruta.exists():  # ya bajado antes: no se vuelve a pedir a la CNE
        contenido = ruta.read_bytes()
    else:
        try:
            pedido = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (vigia-ernc)"})
            with urllib.request.urlopen(pedido, timeout=60) as respuesta:
                contenido = respuesta.read()
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as e:
            print(f"  {edicion}: faltante ({e})")
            return registro
        if not es_pdf(contenido):
            print(f"  {edicion}: faltante (la respuesta no es un PDF)")
            return registro
        carpeta.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(contenido)

    registro["sha256"] = hashlib.sha256(contenido).hexdigest()
    registro["descargado"] = datetime.fromtimestamp(ruta.stat().st_mtime).isoformat(timespec="seconds")
    registro["estado"] = "ok"
    print(f"  {edicion}: ok ({len(contenido) // 1024} KB, sha256 {registro['sha256'][:12]}...)")
    return registro


def descargar_todo(lista=None):
    return [descargar_edicion(e) for e in (lista or ediciones())]
