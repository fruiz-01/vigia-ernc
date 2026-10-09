"""Línea de comandos: python -m vigia <paso>

  todo          descargar + extraer + validar + publicar
  descargar     baja los reportes mensuales de la CNE
  extraer       lee las tablas con el modelo (o desde la caché)
  validar       aplica las siete reglas y guarda en SQLite
  publicar      escribe el informe en docs/informe.html
  precision     compara al modelo con la transcripción manual
  sql "..."     consulta la base
  escritorio    graba las órdenes y escribe docs/index.html
"""
import json
import os
import sys
from collections import Counter
from pathlib import Path

from vigia import base, descargar, escritorio, extraer, leer, precision, publicar, validar


def paso_descargar(con):
    print("Descargando reportes de la CNE...")
    registros = descargar.descargar_todo()
    base.guardar_reportes(con, registros)
    faltan = [r["edicion"] for r in registros if r["estado"] == "faltante"]
    print(f"{len(registros) - len(faltan)} descargados, faltantes: {', '.join(faltan) or 'ninguno'}")


def ediciones_ok(con):
    return [r["edicion"] for r in con.execute("SELECT edicion FROM reportes WHERE estado = 'ok' ORDER BY edicion")]


def paso_extraer(con):
    print("Extrayendo tablas con el modelo...")
    cliente = None
    if os.environ.get("ANTHROPIC_API_KEY"):
        import anthropic
        cliente = anthropic.Anthropic()
    for edicion in ediciones_ok(con):
        if not (extraer.CARPETA / f"{edicion}.json").exists() and cliente is None:
            print(f"  {edicion}: sin caché y sin ANTHROPIC_API_KEY, se omite")
            continue
        paginas = leer.leer_tablas(descargar.CARPETA / f"{edicion}.pdf")
        try:
            resultado = extraer.extraer_edicion(edicion, paginas, cliente)
            via = f" · leído vía {resultado['via'].split(',')[0]}" if resultado.get("via") else ""
            print(f"  {edicion}: {len(resultado['intentos'][-1]['filas'])} filas "
                  f"({len(resultado['intentos'])} intento(s)){via}")
        except Exception as e:  # una edición con problemas no detiene el resto
            print(f"  {edicion}: ERROR {e}")


def paso_validar(con):
    print("Validando con las siete reglas...")
    resumen, por_regla, reintentos = Counter(), Counter(), 0
    for edicion in ediciones_ok(con):
        ruta = extraer.CARPETA / f"{edicion}.json"
        if not ruta.exists():
            print(f"  {edicion}: sin extracción, se omite")
            continue
        intentos = json.loads(ruta.read_text(encoding="utf-8"))["intentos"]
        final = intentos[-1]  # el último intento es el que vale
        reintentos += len(intentos) - 1
        paginas = leer.leer_tablas(descargar.CARPETA / f"{edicion}.pdf")
        textos = {etapa: p["texto"] for etapa, p in paginas.items()}
        controles = validar.validar_edicion(edicion, final, textos, base.filas_previas(con, edicion))
        base.guardar_edicion(con, edicion, paginas, final["filas"], controles)
        malos = [c for c in controles if c["resultado"] != "ok"]
        resumen.update(c["resultado"] for c in controles)
        por_regla.update(f"{c['regla']} ({c['resultado']})" for c in malos)
        print(f"  {edicion}: {len(final['filas'])} filas, "
              f"{sum(c['resultado'] == 'error' for c in controles)} errores, "
              f"{sum(c['resultado'] == 'aviso' for c in controles)} avisos")
        for c in malos:
            print(f"      [{c['resultado']}] {c['etapa']} · {c['regla']}: {c['detalle']}")
    print(f"Controles: {dict(resumen)} · reintentos usados: {reintentos}")
    for regla, n in sorted(por_regla.items()):
        print(f"  {regla}: {n}")


def paso_precision(con):
    """Compara la extracción del modelo con las referencias transcritas a mano (tests/datos)."""
    print("Precisión contra la referencia manual...")
    for ruta_ref in sorted(Path("tests/datos").glob("esperado_*.json")):
        edicion = ruta_ref.stem.split("_")[1]
        ruta = extraer.CARPETA / f"{edicion}.json"
        if not ruta.exists():
            print(f"  {edicion}: sin extracción del modelo")
            continue
        referencia = json.loads(ruta_ref.read_text(encoding="utf-8"))["filas"]
        modelo = json.loads(ruta.read_text(encoding="utf-8"))["intentos"][-1]["filas"]
        aciertos, total, diferencias = precision.comparar(modelo, referencia)
        print(f"  {edicion}: {aciertos} de {total} campos correctos")
        for d in diferencias:
            print(f"      {d}")


def paso_publicar(con):
    print(f"Página escrita en {publicar.publicar(con)}")


def paso_sql(con, consulta):
    cursor = con.execute(consulta)
    columnas = [c[0] for c in cursor.description]
    filas = [["" if v is None else f"{v:g}" if isinstance(v, float) else str(v) for v in f] for f in cursor]
    anchos = [max(len(x) for x in [col, *(f[i] for f in filas)]) for i, col in enumerate(columnas)]
    for linea in [columnas, ["-" * a for a in anchos], *filas]:
        print("  ".join(x.ljust(a) for x, a in zip(linea, anchos)).rstrip())


def paso_escritorio(con):
    print("Grabando las órdenes de la terminal...")
    print(f"Escritorio escrito en {escritorio.generar()}")


def paso_vista_previa(con):
    print(f"Vista previa escrita en {publicar.vista_previa()}")


def main(argv):
    pasos = {"descargar": [paso_descargar], "extraer": [paso_extraer], "validar": [paso_validar],
             "publicar": [paso_publicar], "todo": [paso_descargar, paso_extraer, paso_validar, paso_publicar],
             "precision": [paso_precision], "vista-previa": [paso_vista_previa],
             "escritorio": [paso_escritorio]}
    sys.stdout.reconfigure(errors="replace")  # la consola de Windows no siempre acepta tildes y comillas «»
    if len(argv) == 2 and argv[0] == "sql":
        paso_sql(base.conectar(), argv[1])
        return 0
    if len(argv) != 1 or argv[0] not in pasos:
        print(__doc__)
        return 1
    con = base.conectar()
    for paso in pasos[argv[0]]:
        paso(con)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
