"""Genera la página del informe: un solo HTML estático, listo para GitHub Pages.

    publicar(con, ruta)   lee la base (reportes, filas, controles) y escribe el HTML
    vista_previa()        arma una base en memoria con las ediciones transcritas a mano
                          (tests/datos) para ver la página antes de correr el modelo
"""
import json
from datetime import date
from html import escape
from pathlib import Path

from vigia import base, descargar, leer, validar

# Regiones de norte a sur: el orden de los gráficos sigue la geografía de Chile.
REGIONES = {
    "XV": "Arica y Parinacota", "I": "Tarapacá", "II": "Antofagasta", "III": "Atacama",
    "IV": "Coquimbo", "V": "Valparaíso", "RM": "Metropolitana", "VI": "O'Higgins",
    "VII": "Maule", "XVI": "Ñuble", "VIII": "Biobío", "IX": "Araucanía", "XIV": "Los Ríos",
    "X": "Los Lagos", "XI": "Aysén", "XII": "Magallanes",
}
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]
NOMBRE_REGLA = {"totales": "Totales", "conteo": "Conteo", "evidencia": "Evidencia", "fecha_en_mes": "Fecha",
                "rango": "Rango", "faltante": "Faltante", "duplicado": "Duplicado"}
GRAVEDAD = {"ok": 0, "aviso": 1, "error": 2}
TECNOLOGIAS = {"solar": "Solar", "eolica": "Eólica", "mixto": "Mixto", "otra": "Otra"}

# Fichas: supuestos para conversar con el área de Mercados, no verdades.
FICHA_MW_MIN, FICHA_MW_MAX, FICHAS = 20, 300, 6


# ── Formatos ────────────────────────────────────────────────────────────────

def numero(valor, decimales=0):
    """Formato chileno: 1.234,5"""
    if valor is None:
        return "—"
    texto = f"{valor:,.{decimales}f}"
    return texto.replace(",", "_").replace(".", ",").replace("_", ".")


def edicion_larga(edicion):
    return f"{MESES[int(edicion[4:]) - 1]} {edicion[:4]}"


def fecha_corta(iso):
    if not iso:
        return "—"
    d = date.fromisoformat(iso)
    return f"{d.day} {MESES[d.month - 1][:3]} {d.year}"


def region(codigo):
    return REGIONES.get(codigo, codigo)


def tecnologia(texto):
    """Agrupa las variantes que trae la fuente («Solar - PV», «Solar -  PV», «Eólica», «Mixto»)."""
    t = (texto or "").lower()
    if "solar" in t or "fotovolt" in t:
        return "solar"
    if "eól" in t or "eol" in t:
        return "eolica"
    if "mixt" in t:
        return "mixto"
    return "otra"


def punto(clave_tecnologia):
    return f'<i class="punto t-{clave_tecnologia}"></i>'


def marca(resultado):
    nombres = {"ok": "sin observaciones", "aviso": "aviso", "error": "error"}
    return f'<i class="m m-{resultado}" title="{nombres[resultado]}"></i><span class="sr">{nombres[resultado]}</span>'


# ── Lectura de la base ──────────────────────────────────────────────────────

def leer_base(con):
    reportes = [dict(r) for r in con.execute("SELECT * FROM reportes ORDER BY edicion")]
    filas = [dict(f) for f in con.execute("SELECT * FROM filas ORDER BY fecha DESC, nombre")]
    controles = [dict(c) for c in con.execute("SELECT * FROM controles")]
    return reportes, filas, controles


def fichas(filas):
    """Aprobados con baterías y tamaño intermedio, de mayor a menor potencia."""
    candidatos = [f for f in filas if f["etapa"] == "aprobacion" and f["almacenamiento"]
                  and f["potencia_mw"] and FICHA_MW_MIN <= f["potencia_mw"] <= FICHA_MW_MAX]
    unicos = {}
    for f in sorted(candidatos, key=lambda f: -f["potencia_mw"]):
        unicos.setdefault(f["clave"], f)  # una ficha por proyecto, aunque se repita en otra edición
    return list(unicos.values())[:FICHAS]


# ── Bloques de la página ────────────────────────────────────────────────────

def bloque_cifras(reportes, filas, controles):
    leidas = sorted({f["edicion"] for f in filas})
    mw = sum(f["potencia_mw"] or 0 for f in filas)
    errores = sum(c["resultado"] == "error" for c in controles)
    avisos = sum(c["resultado"] == "aviso" for c in controles)
    cifra = lambda v, d=0: f'<span data-cuenta="{v}" data-decimales="{d}">{numero(v, d)}</span>'
    return f"""
    <dl class="cifras">
      <div><dt>Filas leídas</dt><dd>{cifra(len(filas))}</dd><dd class="nota">{len(leidas)} de {len(reportes)} ediciones</dd></div>
      <div><dt>Potencia</dt><dd>{cifra(mw)} <small>MW</small></dd><dd class="nota">ingresos y aprobaciones</dd></div>
      <div><dt>Controles</dt><dd>{cifra(len(controles))}</dd><dd class="nota">7 reglas por tabla</dd></div>
      <div><dt>Observaciones</dt><dd><span class="{'rojo' if errores else 'verde'}">{cifra(errores)}</span> <small>errores</small> · <span class="ambar">{cifra(avisos)}</span> <small>avisos</small></dd><dd class="nota">cada una explicada abajo</dd></div>
    </dl>"""


def grafico_regiones(filas):
    """Barras horizontales por región, de norte a sur, apiladas por tecnología."""
    por_region = {}
    for f in filas:
        if f["potencia_mw"]:
            t = tecnologia(f["tecnologia"])
            por_region.setdefault(f["region"], {}).setdefault(t, 0)
            por_region[f["region"]][t] += f["potencia_mw"]
    if not por_region:
        return ""
    maximo = max(sum(v.values()) for v in por_region.values())
    orden = [r for r in REGIONES if r in por_region] + [r for r in por_region if r not in REGIONES]
    filas_html = []
    for k, r in enumerate(orden):
        tramos = "".join(
            f'<span class="t-{t}" style="width:{mw / maximo * 100:.2f}%" title="{TECNOLOGIAS[t]}: {numero(mw)} MW"></span>'
            for t, mw in sorted(por_region[r].items(), key=lambda x: list(TECNOLOGIAS).index(x[0])))
        filas_html.append(f'<div class="region"><span class="nombre">{region(r)}</span>'
                          f'<span class="pista" style="--i:{k}">{tramos}</span>'
                          f'<span class="valor">{numero(sum(por_region[r].values()))}</span></div>')
    return f"""
      <figure class="grafico">
        <figcaption>Potencia por región, de norte a sur <span>MW</span></figcaption>
        <div class="regiones">{"".join(filas_html)}</div>
      </figure>"""


def grafico_meses(reportes, filas):
    """Columnas por edición: ingresos y aprobados. Las ediciones sin datos quedan a la vista."""
    suma = {}
    for f in filas:
        suma.setdefault(f["edicion"], {"ingreso": 0, "aprobacion": 0})[f["etapa"]] += f["potencia_mw"] or 0
    maximo = max([v for s in suma.values() for v in s.values()] + [1])
    columnas = []
    for k, r in enumerate(reportes):
        ed = r["edicion"]
        etiqueta = f'{MESES[int(ed[4:]) - 1][:3]}<br><span>{ed[2:4]}</span>'
        if r["estado"] == "faltante":
            cuerpo, clase, titulo = "", " falta", "no está publicado"
        elif ed not in suma:
            cuerpo, clase, titulo = "", " pendiente", "espera la lectura del modelo"
        else:
            s = suma[ed]
            cuerpo = (f'<span class="barra e-ingreso" style="height:{s["ingreso"] / maximo * 100:.1f}%;--i:{k}"></span>'
                      f'<span class="barra e-aprobacion" style="height:{s["aprobacion"] / maximo * 100:.1f}%;--i:{k}"></span>')
            clase, titulo = "", f'ingresos {numero(s["ingreso"])} MW · aprobados {numero(s["aprobacion"])} MW'
        columnas.append(f'<div class="mes{clase}" title="{edicion_larga(ed)}: {titulo}"><div class="area">{cuerpo}</div>'
                        f'<div class="etiqueta">{etiqueta}</div></div>')
    return f"""
      <figure class="grafico">
        <figcaption>Potencia por edición del reporte <span>MW</span></figcaption>
        <div class="meses">{"".join(columnas)}</div>
        <p class="leyenda"><span><i class="cuadro e-ingreso"></i>Ingresa a evaluación</span><span><i class="cuadro e-aprobacion"></i>Aprobado</span><span><i class="cuadro rayado"></i>Sin datos</span></p>
      </figure>"""


def bloque_graficos(reportes, filas):
    leyenda = "".join(f"<span>{punto(t)}{n}</span>" for t, n in TECNOLOGIAS.items()
                      if any(tecnologia(f["tecnologia"]) == t for f in filas))
    return f"""
    <section class="aparece">
      <div class="graficos">
        {grafico_regiones(filas)}
        {grafico_meses(reportes, filas)}
      </div>
      <p class="leyenda">{leyenda}</p>
    </section>"""


def bloque_verificacion(reportes, controles):
    encabezado = "".join(f"<th>{n}</th>" for n in NOMBRE_REGLA.values())
    filas_html, detalles = [], []
    for r in reportes:
        ed = r["edicion"]
        propios = [c for c in controles if c["edicion"] == ed]
        clase = ""
        if r["estado"] == "faltante":
            celdas = '<td colspan="7">No está publicado en la dirección esperada; se registra y se sigue</td>'
            estado, clase = '<span class="etiqueta-estado rojo">Falta</span>', ' class="falta"'
        elif not propios:
            celdas = '<td colspan="7">Descargado; espera la lectura del modelo</td>'
            estado, clase = '<span class="etiqueta-estado">Pendiente</span>', ' class="pendiente"'
        else:
            celdas = ""
            for regla in NOMBRE_REGLA:
                peor = max((c["resultado"] for c in propios if c["regla"] == regla), key=GRAVEDAD.get, default="ok")
                celdas += f'<td class="c">{marca(peor)}</td>'
            n_err = sum(c["resultado"] == "error" for c in propios)
            estado = (f'<span class="etiqueta-estado rojo">{n_err} error{"es" if n_err > 1 else ""}</span>' if n_err
                      else '<span class="etiqueta-estado verde">Verificado</span>')
            for c in propios:
                if c["resultado"] != "ok":
                    detalles.append(f'<li>{marca(c["resultado"])}<b>{edicion_larga(ed)}</b> · '
                                    f'{"ingresos" if c["etapa"] == "ingreso" else "aprobados"} · '
                                    f'{NOMBRE_REGLA[c["regla"]]}: {escape(c["detalle"])}</li>')
        filas_html.append(f'<tr{clase}><td class="ed">{edicion_larga(ed)}</td><td>{estado}</td>{celdas}</tr>')
    lista = f'<ul class="detalles">{"".join(detalles)}</ul>' if detalles else ""
    return f"""
    <section class="aparece">
      <h2>Verificación</h2>
      <div class="tabla"><table class="verificacion">
        <thead><tr><th>Edición</th><th>Estado</th>{encabezado}</tr></thead>
        <tbody>{"".join(filas_html)}</tbody>
      </table></div>
      {lista}
    </section>"""


def bloque_fichas(seleccion, reportes):
    url = {r["edicion"]: r["url"] for r in reportes}
    if not seleccion:
        return ""
    piezas = []
    for k, f in enumerate(seleccion):
        t = tecnologia(f["tecnologia"])
        intensidad = f["inversion_musd"] / f["potencia_mw"] if f["inversion_musd"] is not None else None
        fuera = intensidad is not None and not (0.3 <= intensidad <= 3.0)
        piezas.append(f"""
      <article class="ficha f-{t}" style="--i:{k}">
        <p class="meta">{punto(t)}{TECNOLOGIAS[t]} · {region(f["region"])} · aprobado el {fecha_corta(f["fecha"])}</p>
        <h3>{escape(f["nombre"])}</h3>
        <p class="titular">{escape(f["titular"])}</p>
        <dl class="datos">
          <div><dt>Potencia</dt><dd>{numero(f["potencia_mw"])} MW</dd></div>
          <div><dt>Inversión</dt><dd>{numero(f["inversion_musd"])} MMUSD</dd></div>
          <div><dt>Por MW</dt><dd{' class="ambar"' if fuera else ""}>{numero(intensidad, 2)}</dd></div>
          <div><dt>Baterías</dt><dd>Sí</dd></div>
        </dl>
        <p class="falta"><span>Falta confirmar en el expediente del SEA:</span> MWh de baterías, punto de conexión, fecha de operación y si ya tiene contrato de venta.</p>
        <p class="fuente">Fuente: <a href="{escape(url.get(f["edicion"], "#"))}">CNE, Reporte Mensual ERNC, {edicion_larga(f["edicion"])}</a>, página {f["pagina"]}</p>
      </article>""")
    return f"""
    <section class="aparece">
      <h2>Fichas de oportunidad</h2>
      <p class="criterio">Proyectos con RCA aprobada, con baterías y entre {FICHA_MW_MIN} y {FICHA_MW_MAX} MW, de mayor a menor potencia. Son posibles vendedores de energía para una comercializadora sin centrales propias; el criterio es un supuesto para conversar con el área de Mercados.</p>
      <div class="fichas">{"".join(piezas)}</div>
    </section>"""


def bloque_proyectos(filas):
    cuerpo = "".join(f"""
        <tr>
          <td><span class="etapa e-{f["etapa"]}">{"Aprobado" if f["etapa"] == "aprobacion" else "Ingresa"}</span></td>
          <td class="n">{fecha_corta(f["fecha"])}</td>
          <td>{escape(f["nombre"])}</td>
          <td class="tenue">{escape(f["titular"])}</td>
          <td>{region(f["region"])}</td>
          <td class="sin-corte">{punto(tecnologia(f["tecnologia"]))}{TECNOLOGIAS[tecnologia(f["tecnologia"])]}</td>
          <td class="n">{numero(f["potencia_mw"])}</td>
          <td class="n">{numero(f["inversion_musd"])}</td>
          <td>{"Sí" if f["almacenamiento"] else "—"}</td>
        </tr>""" for f in filas)
    return f"""
    <section class="aparece">
      <h2>Proyectos</h2>
      <div class="tabla"><table>
        <thead><tr><th>Etapa</th><th class="n">Fecha</th><th>Proyecto</th><th>Titular</th><th>Región</th><th>Tecnología</th><th class="n">MW</th><th class="n">MMUSD</th><th>Baterías</th></tr></thead>
        <tbody>{cuerpo}</tbody>
      </table></div>
    </section>"""


METODO = """
    <section class="metodo aparece">
      <h2>Método</h2>
      <ol class="pasos">
        <li><b>Descarga</b><span>Cada mes la CNE publica en PDF el Reporte Mensual ERNC. Se descarga con su huella SHA-256; si una edición no está, se registra.</span></li>
        <li><b>Lectura</b><span>Las tablas no se extraen limpias: nombres partidos en varias líneas y formatos que cambian entre meses. Un modelo de lenguaje (Claude) las lee y devuelve filas con un esquema fijo.</span></li>
        <li><b>Verificación</b><span>Siete reglas revisan lo extraído antes de guardarlo. Si las sumas no cuadran con lo que declara el reporte, el modelo reintenta una vez; si sigue fallando, queda para revisión manual.</span></li>
        <li><b>Publicación</b><span>Base SQLite y esta página, regenerada con un comando.</span></li>
      </ol>
      <dl class="reglas">
        <div><dt>Totales</dt><dd>La suma de MW e inversión coincide con lo que declara el texto del reporte.</dd></div>
        <div><dt>Conteo</dt><dd>El número de filas coincide con los proyectos declarados.</dd></div>
        <div><dt>Evidencia</dt><dd>Cada valor extraído aparece en el texto de la página.</dd></div>
        <div><dt>Fecha</dt><dd>La fecha cae en el mes que cubre la edición.</dd></div>
        <div><dt>Rango</dt><dd>La inversión por MW está entre 0,3 y 3 MMUSD.</dd></div>
        <div><dt>Faltante</dt><dd>Un dato que la fuente trae como «-» queda vacío, no en cero.</dd></div>
        <div><dt>Duplicado</dt><dd>Un proyecto no se repite en la misma etapa, ni en la misma edición ni en otra.</dd></div>
      </dl>
    </section>"""

ESTILOS = """
:root {
  --fondo: #fbfaf6; --banda: #eef3ef; --linea-banda: #d6e2da;
  --tinta: #1d2a26; --tinta-2: #4c5a55; --tenue: #7b8782; --regla: #e3e2da;
  --solar: #e9a21b; --eolica: #1f8a9b; --mixto: #7c5cb3; --otra: #8a9a3f;
  --ingreso: #3c78c3; --aprobacion: #2e8b57;
  --verde: #2e8b57; --rojo: #c8442f; --ambar: #b7791f;
}
@media (prefers-color-scheme: dark) { :root {
  --fondo: #121816; --banda: #18221f; --linea-banda: #26332e;
  --tinta: #e9eeeb; --tinta-2: #b4c0bb; --tenue: #84918c; --regla: #26302c;
  --solar: #f2b33d; --eolica: #3fb0c1; --mixto: #a487d6; --otra: #a9bb5c;
  --ingreso: #6aa1e3; --aprobacion: #4fb57a; --verde: #4fb57a; --rojo: #ee6b55; --ambar: #e3a54a; } }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin:0; background:var(--fondo); color:var(--tinta); font:15px/1.55 'Archivo', system-ui, sans-serif;
       font-variant-numeric: tabular-nums; -webkit-font-smoothing: antialiased; }
.contenido { max-width: 1180px; margin: 0 auto; padding: 0 40px; }
h1, h2, h3, p, dl, dd, ol, ul, figure { margin: 0; }
small { font-size: .55em; font-weight: 500; color: var(--tinta-2); }

/* Cabecera en una banda de color suave, con una franja de las tres tecnologías */
.cabecera { background: var(--banda); border-bottom: 1px solid var(--linea-banda); position: relative; }
.cabecera::before { content: ""; position: absolute; inset: 0 0 auto 0; height: 4px;
  background: linear-gradient(90deg, var(--solar) 0 34%, var(--eolica) 34% 67%, var(--aprobacion) 67%); }
.cabecera .contenido { padding-top: 56px; padding-bottom: 36px; }
.sobretitulo { font-size: 13px; font-weight: 600; color: var(--eolica); letter-spacing: .02em; }
h1 { margin-top: 6px; font-size: 60px; line-height: .95; font-stretch: 70%; font-weight: 750; }
h1 span { color: var(--eolica); }
.bajada { margin-top: 14px; color: var(--tinta-2); max-width: 64ch; font-size: 17px; }
.aviso-previa { margin-top: 16px; display: inline-block; padding: 6px 12px; border-left: 3px solid var(--ambar);
  background: color-mix(in srgb, var(--ambar) 10%, transparent); color: var(--tinta-2); font-size: 14px; max-width: 80ch; }
.cifras { display: flex; flex-wrap: wrap; margin-top: 34px; gap: 0; }
.cifras div { padding: 0 34px 0 0; margin-right: 34px; border-right: 1px solid var(--linea-banda); }
.cifras div:last-child { border: 0; }
.cifras dt { font-size: 13px; color: var(--tinta-2); }
.cifras dd { font-size: 34px; font-weight: 650; font-stretch: 85%; line-height: 1.15; }
.cifras dd.nota { font-size: 13px; font-weight: 400; font-stretch: 100%; color: var(--tenue); }

section { margin-top: 64px; }
h2 { font-size: 18px; font-stretch: 82%; margin-bottom: 16px; display: flex; align-items: center; gap: 10px; }
h2::before { content: ""; width: 14px; height: 3px; background: var(--eolica); border-radius: 2px; }

/* Gráficos */
.graficos { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 32px 64px; }
.grafico figcaption { font-weight: 650; font-stretch: 85%; font-size: 15px; margin-bottom: 14px; }
.grafico figcaption span { font-weight: 400; color: var(--tenue); font-size: 13px; margin-left: 4px; }
.region { display: grid; grid-template-columns: 9.5rem minmax(0, 1fr) 3.5rem; align-items: center; gap: 12px; padding: 4px 0; font-size: 14px; }
.region .nombre { color: var(--tinta-2); }
.region .valor { text-align: right; font-weight: 600; }
.pista { display: flex; height: 14px; border-radius: 3px; overflow: hidden; transform-origin: left;
  animation: crecer-x .9s cubic-bezier(.2,.7,.2,1) both; animation-delay: calc(var(--i) * 60ms + 150ms); }
.pista span { display: block; height: 100%; }
.meses { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 6px; align-items: end; }
.mes .area { height: 170px; display: flex; align-items: flex-end; justify-content: center; gap: 3px;
  border-bottom: 1px solid var(--tinta-2); position: relative; }
.barra { width: 42%; max-width: 14px; border-radius: 2px 2px 0 0; transform-origin: bottom;
  animation: crecer-y .9s cubic-bezier(.2,.7,.2,1) both; animation-delay: calc(var(--i) * 50ms + 200ms); }
.mes.pendiente .area, .mes.falta .area { background: repeating-linear-gradient(135deg, transparent 0 5px, var(--regla) 5px 6px); }
.mes.falta .area { background: repeating-linear-gradient(135deg, transparent 0 5px, color-mix(in srgb, var(--rojo) 35%, transparent) 5px 6px); }
.mes.falta .etiqueta, .mes.falta .etiqueta span { color: var(--rojo); font-weight: 600; }
.etiqueta { text-align: center; font-size: 12px; color: var(--tinta-2); margin-top: 6px; line-height: 1.2; }
.etiqueta span { color: var(--tenue); font-size: 11px; }
.leyenda { display: flex; flex-wrap: wrap; gap: 6px 20px; margin-top: 16px; font-size: 13px; color: var(--tinta-2); }
.leyenda span { display: inline-flex; align-items: center; gap: 7px; }
.cuadro { display: inline-block; width: 11px; height: 11px; border-radius: 2px; }
.cuadro.rayado { background: repeating-linear-gradient(135deg, transparent 0 2px, var(--tenue) 2px 3px); }
.t-solar { background: var(--solar); } .t-eolica { background: var(--eolica); }
.t-mixto { background: var(--mixto); } .t-otra { background: var(--otra); }
.e-ingreso { background: var(--ingreso); } .e-aprobacion { background: var(--aprobacion); }
.punto { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 7px; vertical-align: .02em; }

/* Tablas */
.tabla { position: relative; overflow-x: auto; margin: 0 -10px; } /* contiene a los .sr absolutos */
table { width: 100%; border-collapse: collapse; font-size: 14px; }
th { text-align: left; font-size: 12.5px; font-weight: 600; font-stretch: 87%; color: var(--tinta-2);
     padding: 0 10px 8px; border-bottom: 1.5px solid var(--tinta-2); white-space: nowrap; }
td { padding: 9px 10px; border-bottom: 1px solid var(--regla); vertical-align: baseline; }
tbody tr { transition: background .15s; }
tbody tr:hover { background: color-mix(in srgb, var(--eolica) 6%, transparent); }
.n { text-align: right; white-space: nowrap; }
.c { text-align: center; }
.sin-corte { white-space: nowrap; }
.verificacion th:nth-child(n+3) { text-align: center; }
.verificacion .ed { white-space: nowrap; font-weight: 500; }
.verificacion tr.pendiente td, .verificacion tr.falta td { color: var(--tenue); font-size: 13.5px; }
.verificacion tr.falta { background: color-mix(in srgb, var(--rojo) 5%, transparent); }
.etiqueta-estado { font-size: 13px; font-weight: 600; color: var(--tenue); }
.etiqueta-estado.rojo { color: var(--rojo); } .etiqueta-estado.verde { color: var(--verde); }
.tenue { color: var(--tenue); } .rojo { color: var(--rojo); } .ambar { color: var(--ambar); } .verde { color: var(--verde); }
.m { display: inline-block; vertical-align: 0; }
.m-ok { width: 8px; height: 8px; border-radius: 50%; background: color-mix(in srgb, var(--verde) 70%, transparent); }
.m-aviso { width: 9px; height: 9px; background: var(--ambar); transform: rotate(45deg) scale(.86); }
.m-error { width: 9px; height: 9px; background: var(--rojo); }
.detalles { list-style: none; padding: 0; margin-top: 18px; font-size: 14px; color: var(--tinta-2); }
.detalles li { padding: 7px 0; border-bottom: 1px solid var(--regla); }
.detalles .m { margin-right: 10px; }
.detalles b { color: var(--tinta); font-weight: 600; }
.etapa { font-size: 13px; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
.etapa::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.etapa.e-ingreso, .etapa.e-aprobacion { background: none; }
.etapa.e-ingreso { color: var(--ingreso); } .etapa.e-aprobacion { color: var(--aprobacion); }

/* Fichas: sin cajas; una línea de color por tecnología marca cada una */
.criterio { color: var(--tinta-2); max-width: 80ch; margin-bottom: 14px; }
.fichas { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 8px 48px; }
.ficha { padding: 16px 0 22px; border-top: 3px solid var(--tenue); }
.ficha.f-solar { border-top-color: var(--solar); } .ficha.f-eolica { border-top-color: var(--eolica); }
.ficha.f-mixto { border-top-color: var(--mixto); }
.ficha .meta { font-size: 13px; color: var(--tinta-2); }
.ficha h3 { margin-top: 6px; font-size: 22px; font-stretch: 78%; line-height: 1.15; }
.ficha .titular { color: var(--tinta-2); }
.datos { display: grid; grid-template-columns: repeat(4, auto); justify-content: start; gap: 0 26px; margin-top: 12px; }
.datos dt { font-size: 12.5px; color: var(--tenue); white-space: nowrap; }
.datos dd { font-size: 18px; font-weight: 650; white-space: nowrap; }
.falta { margin-top: 12px; font-size: 13.5px; color: var(--tinta-2); }
.falta span { color: var(--tinta); }
.fuente { margin-top: 6px; font-size: 13px; color: var(--tenue); }
a { color: var(--eolica); text-underline-offset: 3px; }

/* Método */
.pasos { list-style: none; padding: 0; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 24px; counter-reset: paso; }
.pasos li { counter-increment: paso; border-top: 1.5px solid var(--regla); padding-top: 10px; color: var(--tinta-2); font-size: 14px; }
.pasos b { display: block; color: var(--tinta); font-size: 15px; margin-bottom: 4px; }
.pasos b::before { content: counter(paso) " "; color: var(--eolica); font-weight: 700; }
.reglas { margin-top: 28px; max-width: 86ch; }
.reglas div { display: grid; grid-template-columns: 8rem 1fr; padding: 7px 0; border-bottom: 1px solid var(--regla); font-size: 14px; }
.reglas dt { font-weight: 600; }
.reglas dd { color: var(--tinta-2); }
footer { margin: 72px 0 0; padding: 18px 0 40px; border-top: 1px solid var(--regla); font-size: 13px; color: var(--tenue); }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }

/* Animaciones: crecen las barras y las secciones aparecen al llegar a ellas */
@keyframes crecer-x { from { transform: scaleX(0); } }
@keyframes crecer-y { from { transform: scaleY(0); } }
.js .aparece { opacity: 0; transform: translateY(14px); transition: opacity .6s ease, transform .6s ease; }
.js .aparece.visible { opacity: 1; transform: none; }
.js .aparece .pista, .js .aparece .barra { animation-play-state: paused; }
.js .aparece.visible .pista, .js .aparece.visible .barra { animation-play-state: running; }
@media (prefers-reduced-motion: reduce) {
  *, *::before { animation: none !important; transition: none !important; }
  .js .aparece { opacity: 1; transform: none; }
}
@media (max-width: 860px) { .graficos { grid-template-columns: 1fr; } .pasos { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px) { .contenido { padding: 0 16px; } h1 { font-size: 42px; }
  .cabecera .contenido { padding-top: 40px; }
  .cifras div { padding-right: 18px; margin-right: 18px; margin-bottom: 12px; } .cifras dd { font-size: 26px; }
  .region { grid-template-columns: 7rem minmax(0, 1fr) 3rem; }
  .meses { gap: 3px; } .mes .area { height: 130px; }
  .datos { grid-template-columns: repeat(2, auto); } .pasos { grid-template-columns: 1fr; }
  .reglas div { grid-template-columns: 1fr; } }
"""

# Cifras que cuentan desde cero y secciones que aparecen al hacer scroll. Sin JS, todo se ve igual.
SCRIPT = """
document.documentElement.classList.add('js');
const quieto = matchMedia('(prefers-reduced-motion: reduce)').matches;
const formato = (v, d) => v.toLocaleString('es-CL', { minimumFractionDigits: d, maximumFractionDigits: d });
for (const el of document.querySelectorAll('[data-cuenta]')) {
  const fin = Number(el.dataset.cuenta), d = Number(el.dataset.decimales || 0);
  if (quieto || !fin) continue;
  const t0 = performance.now();
  const paso = (t) => {
    const p = Math.min(1, Math.max(0, (t - t0) / 1100)), suave = 1 - Math.pow(1 - p, 3);
    el.textContent = formato(fin * suave, d);
    if (p < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}
const observador = new IntersectionObserver((entradas) => {
  for (const e of entradas) if (e.isIntersecting) { e.target.classList.add('visible'); observador.unobserve(e.target); }
}, { threshold: 0.12 });
document.querySelectorAll('.aparece').forEach((s) => observador.observe(s));
"""


def pagina(reportes, filas, controles, aviso=None):
    aviso_html = f'<p class="aviso-previa">{escape(aviso)}</p>' if aviso else ""
    return f"""<!doctype html>
<html lang="es-CL">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Vigía ERNC</title>
<meta name="description" content="Proyectos ERNC que entran a evaluación ambiental y se aprueban en Chile, leídos de los reportes de la CNE por un agente y verificados antes de guardarse.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@62..125,400..800&display=swap" rel="stylesheet">
<style>{ESTILOS}</style>
<script>document.documentElement.classList.add('js');</script>
</head>
<body>
<header class="cabecera">
  <div class="contenido">
    <p class="sobretitulo">Mercado eléctrico chileno · energías renovables</p>
    <h1>Vigía <span>ERNC</span></h1>
    <p class="bajada">Proyectos que entran a evaluación ambiental y se aprueban en Chile. Un agente los lee de los reportes mensuales de la CNE y los verifica antes de guardarlos.</p>
    {aviso_html}
    {bloque_cifras(reportes, filas, controles)}
  </div>
</header>
<main class="contenido">
  {bloque_graficos(reportes, filas)}
  {bloque_verificacion(reportes, controles)}
  {bloque_fichas(fichas(filas), reportes)}
  {bloque_proyectos(filas)}
  {METODO}
  <footer>Prototipo de Francisco Ruiz · Datos públicos de la Comisión Nacional de Energía · Generado el {fecha_corta(date.today().isoformat())}</footer>
</main>
<script>{SCRIPT}</script>
</body>
</html>
"""


def publicar(con, ruta=Path("docs/informe.html"), aviso=None):
    reportes, filas, controles = leer_base(con)
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(pagina(reportes, filas, controles, aviso), encoding="utf-8")
    return ruta


def vista_previa(ruta=Path("salida/vista-previa.html")):
    """Misma página, pero con las ediciones transcritas a mano en lugar de la salida del modelo."""
    con = base.conectar(":memory:")
    reales = base.conectar()
    base.guardar_reportes(con, [dict(r) for r in reales.execute("SELECT * FROM reportes")])
    for ref in sorted(Path("tests/datos").glob("esperado_*.json")):
        extraccion = json.loads(ref.read_text(encoding="utf-8"))
        edicion = extraccion["edicion"]
        paginas = leer.leer_tablas(descargar.CARPETA / f"{edicion}.pdf")
        textos = {etapa: p["texto"] for etapa, p in paginas.items()}
        controles = validar.validar_edicion(edicion, extraccion, textos, base.filas_previas(con, edicion))
        base.guardar_edicion(con, edicion, paginas, extraccion["filas"], controles)
    aviso = ("Vista previa: solo dos ediciones (octubre 2025 y septiembre 2026), transcritas a mano y pasadas "
             "por las mismas siete reglas. El resto espera la lectura del modelo.")
    return publicar(con, ruta, aviso)
