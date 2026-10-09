"""Diagrama del flujo, con los números de la corrida.

Muestra el mecanismo, no solo las etapas: las reglas reciben dos entradas, lo que
propone el modelo y el texto fuente con los totales que declara el reporte; si los
totales no cuadran, el modelo reintenta una vez con la diferencia.

Lo usan el informe (publicar.py) y el escritorio (escritorio.py). En el escritorio
cada caja lleva data-ir con la app que abre; en el informe ese atributo no hace nada.
"""
from html import escape

# Ancho de cada caja, de izquierda a derecha, y geometría común
CAJAS_ANCHO = [150, 150, 150, 204, 160]
SEPARACION = 52
ARRIBA, ALTO = 58, 74


def cajas(reportes, filas, controles, n_fichas):
    ok = sum(r["estado"] == "ok" for r in reportes)
    faltan = [r["edicion"] for r in reportes if r["estado"] != "ok"]
    cuenta = {r: sum(c["resultado"] == r for c in controles) for r in ("ok", "aviso", "error")}
    meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
             "septiembre", "octubre", "noviembre", "diciembre"]
    falta = (f"{meses[int(faltan[0][4:]) - 1]} {faltan[0][:4]}: no publicado" if len(faltan) == 1
             else f"{len(faltan)} no publicados" if faltan else "todos publicados")
    return [
        ("Reportes CNE", f"{ok} PDF mensuales", falta, "archivos:datos/reportes"),
        ("Texto", "PyMuPDF", f"{2 * ok} páginas de tablas", "verificador"),
        ("Claude", "propone las filas", "esquema fijo (Pydantic)", "editor:vigia/extraer.py"),
        ("7 reglas", "verifican cada número",
         f"{cuenta['ok']} ok · {cuenta['aviso']} avisos · {cuenta['error']} errores", "editor:vigia/validar.py"),
        ("SQLite e informe", f"{len(filas)} filas guardadas", f"{n_fichas} fichas de oportunidad", "navegador"),
    ]


def svg(reportes, filas, controles, n_fichas):
    datos = cajas(reportes, filas, controles, n_fichas)
    xs, x = [], 10
    for ancho in CAJAS_ANCHO:
        xs.append(x)
        x += ancho + SEPARACION
    ancho_total = x - SEPARACION + 10
    centro = [xs[i] + CAJAS_ANCHO[i] / 2 for i in range(5)]
    medio_y = ARRIBA + ALTO / 2
    partes = [f'<svg class="dg" viewBox="0 0 {ancho_total:.0f} 196" role="img" '
              'aria-label="Flujo de Vigía ERNC: los reportes de la CNE se convierten en texto, Claude propone las '
              'filas y siete reglas las verifican contra el texto fuente y los totales del reporte antes de guardarlas; '
              'si los totales no cuadran, Claude reintenta una vez.">',
              '<defs>'
              '<marker id="dg-punta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
              '<path class="punta" d="M0 0L10 5L0 10z"/></marker>'
              '<marker id="dg-punta-acento" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
              '<path class="punta acento" d="M0 0L10 5L0 10z"/></marker>'
              '</defs>']

    # Flechas principales, de izquierda a derecha
    for i, rotulo in enumerate(["PDF", "texto", "filas", "guarda"]):
        x1, x2 = xs[i] + CAJAS_ANCHO[i] + 4, xs[i + 1] - 5
        partes.append(f'<line class="linea" x1="{x1:.0f}" y1="{medio_y:.0f}" x2="{x2:.0f}" y2="{medio_y:.0f}" marker-end="url(#dg-punta)"/>'
                      f'<text class="rotulo" x="{(x1 + x2) / 2:.0f}" y="{medio_y - 7:.0f}" text-anchor="middle">{rotulo}</text>')

    # El texto fuente llega directo a las reglas, sin pasar por el modelo
    y_puente = 30
    partes.append(f'<path class="linea acento" d="M{centro[1]:.0f} {ARRIBA - 3} V{y_puente} H{centro[3]:.0f} V{ARRIBA - 5}" '
                  'marker-end="url(#dg-punta-acento)"/>'
                  f'<text class="rotulo acento" x="{(centro[1] + centro[3]) / 2:.0f}" y="{y_puente - 8}" text-anchor="middle">'
                  'texto fuente y totales que declara el reporte: cada valor debe aparecer ahí</text>')

    # Si los totales no cuadran, vuelve al modelo con la diferencia
    y_vuelta = ARRIBA + ALTO + 30
    x_sale = centro[3] - 40
    partes.append(f'<path class="linea discont" d="M{x_sale:.0f} {ARRIBA + ALTO + 3} V{y_vuelta} H{centro[2]:.0f} V{ARRIBA + ALTO + 5}" '
                  'marker-end="url(#dg-punta)"/>'
                  f'<text class="rotulo" x="{(centro[2] + x_sale) / 2:.0f}" y="{y_vuelta + 18}" text-anchor="middle">'
                  'si los totales no cuadran: 1 reintento con la diferencia</text>')

    # Cajas al final, encima de las líneas
    for i, (titulo, sub1, sub2, ir) in enumerate(datos):
        clase = "caja acento" if i == 3 else "caja"
        partes.append(f'<g data-ir="{escape(ir)}" tabindex="-1">'
                      f'<rect class="{clase}" x="{xs[i]}" y="{ARRIBA}" width="{CAJAS_ANCHO[i]}" height="{ALTO}" rx="6"/>'
                      f'<text class="t1" x="{centro[i]:.0f}" y="{ARRIBA + 25}" text-anchor="middle">{escape(titulo)}</text>'
                      f'<text class="t2" x="{centro[i]:.0f}" y="{ARRIBA + 45}" text-anchor="middle">{escape(sub1)}</text>'
                      f'<text class="t2" x="{centro[i]:.0f}" y="{ARRIBA + 62}" text-anchor="middle">{escape(sub2)}</text></g>')
    partes.append("</svg>")
    return "".join(partes)


LEYENDA = ("El modelo propone y las reglas verifican: cada número que devuelve Claude se contrasta con el texto "
           "de la página y con los totales que declara el propio reporte antes de guardarse.")


def figura(reportes, filas, controles, n_fichas):
    return (f'<figure class="flujo">{svg(reportes, filas, controles, n_fichas)}'
            f'<figcaption>{escape(LEYENDA)}</figcaption></figure>')


# Estilos del diagrama; cada página define --dg-acento, --dg-fondo y el color del texto
ESTILOS = """
.flujo { margin: 0; }
.flujo figcaption { margin-top: 10px; font-size: 13.5px; opacity: .8; max-width: 80ch; }
.dg { display: block; width: 100%; height: auto; max-width: 1060px; font-family: inherit; overflow: visible; }
.dg .caja { fill: var(--dg-fondo); stroke: currentColor; stroke-opacity: .35; stroke-width: 1.2; }
.dg .caja.acento { stroke: var(--dg-acento); stroke-opacity: 1; stroke-width: 1.8; }
.dg .t1 { font-size: 13.5px; font-weight: 700; fill: currentColor; }
.dg .t2 { font-size: 11.5px; fill: currentColor; fill-opacity: .72; }
.dg .linea { stroke: currentColor; stroke-opacity: .7; stroke-width: 1.3; fill: none; }
.dg .linea.acento { stroke: var(--dg-acento); stroke-opacity: 1; stroke-width: 1.6; }
.dg .discont { stroke-dasharray: 5 4; }
.dg .rotulo { font-size: 11.5px; fill: currentColor; fill-opacity: .8; }
.dg .rotulo.acento { fill: var(--dg-acento); fill-opacity: 1; font-weight: 600; }
.dg .punta { fill: currentColor; fill-opacity: .7; }
.dg .punta.acento { fill: var(--dg-acento); fill-opacity: 1; }
"""

MERMAID = """```mermaid
flowchart LR
    A["Reportes CNE<br/>11 PDF mensuales"] -->|PDF| B["Texto<br/>PyMuPDF"]
    B -->|texto| C["Claude<br/>propone las filas"]
    C -->|filas| D["7 reglas<br/>verifican cada número"]
    B -. "texto fuente y totales declarados" .-> D
    D -. "si los totales no cuadran:<br/>1 reintento con la diferencia" .-> C
    D -->|guarda| E["SQLite e informe"]
```"""
