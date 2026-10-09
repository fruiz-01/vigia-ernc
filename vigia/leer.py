"""Ubica en el PDF las dos páginas con tablas y devuelve su texto.

La página cambia entre ediciones (6-7 o 7-8), así que se busca por contenido:
la página de la tabla es la que trae el título de la sección y el encabezado
«Titular del proyecto». El índice (página 3) nombra las secciones pero no trae
la tabla, por eso hace falta la segunda condición.
"""
import fitz  # PyMuPDF

# etapa -> título de la sección en el reporte
TITULOS = {
    "ingreso": "Proyectos Ingresados a Evaluación Ambiental",
    "aprobacion": "Proyectos con RCA Aprobada",
}


def etapa_de_pagina(texto):
    """Devuelve 'ingreso', 'aprobacion' o None según lo que contiene la página."""
    if "Titular del proyecto" not in texto:
        return None
    for etapa, titulo in TITULOS.items():
        if titulo in texto:
            return etapa
    return None


def leer_tablas(ruta_pdf):
    """{etapa: {"pagina": n, "texto": str}} para las dos tablas del reporte."""
    paginas = {}
    with fitz.open(ruta_pdf) as pdf:
        for i, pagina in enumerate(pdf, start=1):
            texto = pagina.get_text()
            etapa = etapa_de_pagina(texto)
            if etapa and etapa not in paginas:
                paginas[etapa] = {"pagina": i, "texto": texto}
    faltan = set(TITULOS) - set(paginas)
    if faltan:
        raise ValueError(f"{ruta_pdf}: no se encontró la tabla de {', '.join(sorted(faltan))}")
    return paginas
