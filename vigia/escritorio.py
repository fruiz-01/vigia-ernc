"""Escritorio de demostración: el proyecto dentro de un escritorio Windows, en una sola página.

Pensado para quien revisa la postulación sin instalar nada. Todo lo que muestra
sale de la corrida real:
- la terminal reproduce la salida grabada de cada orden (se graban al generar),
- el verificador muestra el texto de cada página junto a lo que extrajo el modelo
  y el resultado de las siete reglas, leídos de la base,
- los archivos y el editor muestran el código del repositorio tal cual.

python -m vigia escritorio  ->  graba las órdenes y escribe docs/index.html
"""
import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

from vigia import base, diagrama, extraer, publicar
from vigia.notas import NOTAS

PLANTILLA = Path(__file__).with_name("escritorio.html")
DESTINO = Path("docs/index.html")

# Datos de contacto que se muestran en el menú Inicio (vacío = no se muestra)
AUTOR = {
    "nombre": "Francisco Ruiz",
    "cargo": "Ingeniero Civil Industrial",
    "correo": "",
    "linkedin": "",
    "github": "https://github.com/fruiz-01",
    "repo": "https://github.com/fruiz-01/vigia-ernc",
}

# Orden tal como se escribe en la terminal -> argumentos para el intérprete
ORDENES = {
    "python -m vigia": ["-m", "vigia"],
    "python -m vigia todo": ["-m", "vigia", "todo"],
    "python -m vigia descargar": ["-m", "vigia", "descargar"],
    "python -m vigia extraer": ["-m", "vigia", "extraer"],
    "python -m vigia validar": ["-m", "vigia", "validar"],
    "python -m vigia publicar": ["-m", "vigia", "publicar"],
    "python -m vigia precision": ["-m", "vigia", "precision"],
    "pytest -q": ["-m", "pytest", "-q", "-p", "no:cacheprovider"],
}

CONSULTAS = [
    "SELECT etapa, COUNT(*) AS filas, SUM(potencia_mw) AS mw, SUM(inversion_musd) AS mmusd FROM filas GROUP BY etapa",
    "SELECT regla, resultado, COUNT(*) AS n FROM controles GROUP BY regla, resultado ORDER BY regla",
    "SELECT nombre, region, potencia_mw FROM filas WHERE etapa = 'aprobacion' AND almacenamiento = 1 "
    "ORDER BY potencia_mw DESC LIMIT 6",
]
for consulta in CONSULTAS:
    ORDENES[f'python -m vigia sql "{consulta}"'] = ["-m", "vigia", "sql", consulta]

# Archivos del repositorio que se pueden abrir en el escritorio
ARCHIVOS = ["README.md", "requirements.txt", "pytest.ini", ".gitignore", "vigia/*.py",
            "tests/*.py", "tests/datos/*.json", "datos/extracciones/*.json"]


def grabar():
    """Corre cada orden y guarda su salida, tal como la vería quien la escribe."""
    entorno = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    salidas = {}
    for orden, argumentos in ORDENES.items():
        r = subprocess.run([sys.executable, *argumentos], capture_output=True, text=True,
                           encoding="utf-8", env=entorno)
        salidas[orden] = (r.stdout + r.stderr).rstrip("\n")
    return salidas


def archivos():
    lista = []
    for patron in ARCHIVOS:
        for ruta in sorted(Path(".").glob(patron)):
            lista.append({"ruta": ruta.as_posix(), "contenido": ruta.read_text(encoding="utf-8")})
    for pdf in sorted(Path("datos/reportes").glob("*.pdf")):
        lista.append({"ruta": pdf.as_posix(), "tipo": "pdf"})
    lista += [{"ruta": "datos/vigia.sqlite", "tipo": "base"},
              {"ruta": "docs/informe.html", "tipo": "web"},
              {"ruta": "docs/index.html", "tipo": "esta"}]
    for a in lista:
        ruta = Path(a["ruta"])
        a["bytes"] = ruta.stat().st_size if ruta.exists() else None
    return lista


def ediciones(con):
    reportes = [dict(r) for r in con.execute("SELECT * FROM reportes ORDER BY edicion")]
    salida = []
    for r in reportes:
        e = r["edicion"]
        paginas = {p["etapa"]: {"pagina": p["pagina"], "texto": p["texto"]}
                   for p in con.execute("SELECT * FROM paginas WHERE edicion = ?", (e,))}
        filas = [dict(f) for f in con.execute("SELECT * FROM filas WHERE edicion = ? ORDER BY rowid", (e,))]
        controles = [dict(c) for c in con.execute("SELECT * FROM controles WHERE edicion = ? ORDER BY rowid", (e,))]
        cache = extraer.CARPETA / f"{e}.json"
        declarado, intentos, via = {}, 0, None
        if cache.exists():
            datos = json.loads(cache.read_text(encoding="utf-8"))
            final = datos["intentos"][-1]
            declarado = {etapa: final[f"declarado_{etapa}"] for etapa in ("ingreso", "aprobacion")}
            intentos, via = len(datos["intentos"]), datos.get("via")
        salida.append({"edicion": e, "estado": r["estado"], "url": r["url"], "sha256": r["sha256"],
                       "paginas": paginas, "filas": filas, "controles": controles,
                       "declarado": declarado, "intentos": intentos, "via": via})
    return salida


def generar(destino=DESTINO):
    salidas = grabar()  # primero: `todo` y `publicar` regeneran la base y el informe
    con = base.conectar()
    reportes, filas, controles = publicar.leer_base(con)
    datos = {"generado": date.today().isoformat(), "modelo": extraer.MODELO, "autor": AUTOR,
             "consultas": CONSULTAS, "ediciones": ediciones(con), "archivos": archivos(),
             "terminal": salidas, "notas": NOTAS,
             "diagrama": diagrama.svg(reportes, filas, controles, len(publicar.fichas(filas))),
             "leyenda_diagrama": diagrama.LEYENDA}
    # «<» escapado: ni «</script>» ni «<!--» dentro del JSON pueden cortar la etiqueta
    incrustado = json.dumps(datos, ensure_ascii=False).replace("<", "\\u003c")
    html = (PLANTILLA.read_text(encoding="utf-8")
            .replace("/*ESTILOS_DIAGRAMA*/", diagrama.ESTILOS)
            .replace("/*DATOS*/{}", incrustado))
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(html, encoding="utf-8")
    return destino
