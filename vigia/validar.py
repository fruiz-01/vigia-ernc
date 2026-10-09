"""Las siete reglas que verifican lo que extrajo el modelo.

El modelo propone, las reglas verifican. Cada regla es una función pura que
recibe filas (diccionarios) y devuelve un control:
    {"regla": ..., "resultado": "ok" | "aviso" | "error", "detalle": ...}
"""
import re
import unicodedata


def control(regla, resultado, detalle):
    return {"regla": regla, "resultado": resultado, "detalle": detalle}


def normalizar(texto):
    """Texto comparable: sin tildes, en minúsculas y sin espacios, guiones, barras ni puntos.

    Así «CANDE-\\nLARIA», «Solar -  PV» y «30-09- 2025» calzan con «Candelaria»,
    «Solar - PV» y «30092025», aunque el PDF los haya partido en varias líneas.
    """
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))  # quita tildes
    return re.sub(r"[\s\-‐–—/.­]", "", texto.lower())


def numeros_en(texto):
    """Conjunto de números escritos en el texto, sin punto de miles («1.248» -> «1248»)."""
    return {n.replace(".", "") for n in re.findall(r"\d+(?:\.\d{3})*(?:,\d+)?", texto)}


def como_texto(numero):
    """120.0 -> '120'; 9.5 -> '9,5' (así se escribe en el reporte)."""
    return str(int(numero)) if numero == int(numero) else str(numero).replace(".", ",")


def mes_cubierto(edicion):
    """La edición AAAAMM informa el mes anterior: '202609' -> '2026-08'."""
    a, m = int(edicion[:4]), int(edicion[4:])
    a, m = (a - 1, 12) if m == 1 else (a, m - 1)
    return f"{a}-{m:02d}"


def clave(fila):
    """Identidad de un proyecto: nombre y titular normalizados."""
    return normalizar(fila["nombre"]) + "|" + normalizar(fila["titular"])


# --- 1. Totales -----------------------------------------------------------------
def totales(filas, declarado, tolerancia=1):
    """La suma de MW y MMUSD de las filas coincide con lo que declara el texto.

    La tolerancia de 1 cubre el redondeo de las cifras publicadas.
    """
    mw = sum(f["potencia_mw"] or 0 for f in filas)  # potencia «-» cuenta como 0 en la suma
    mmusd = sum(f["inversion_musd"] or 0 for f in filas)
    dif = []
    if abs(mw - declarado["mw"]) > tolerancia:
        dif.append(f"las filas suman {como_texto(mw)} MW y el reporte declara {como_texto(declarado['mw'])}")
    if abs(mmusd - declarado["mmusd"]) > tolerancia:
        dif.append(f"las filas suman {como_texto(mmusd)} MMUSD y el reporte declara {como_texto(declarado['mmusd'])}")
    if dif:
        return control("totales", "error", "; ".join(dif))
    return control("totales", "ok", f"{como_texto(mw)} MW y {como_texto(mmusd)} MMUSD, igual a lo declarado")


# --- 2. Conteo ------------------------------------------------------------------
def conteo(filas, declarado):
    if len(filas) != declarado["proyectos"]:
        return control("conteo", "error",
                       f"hay {len(filas)} filas y el reporte declara {declarado['proyectos']} proyectos")
    return control("conteo", "ok", f"{len(filas)} filas, igual a lo declarado")


# --- 3. Evidencia ---------------------------------------------------------------
def evidencia(filas, declarado, texto):
    """Cada valor extraído tiene que estar escrito en la página (si no, el modelo lo inventó)."""
    plano = normalizar(texto)
    numeros = numeros_en(texto)
    faltan = []
    for f in filas:
        a, m, d = f["fecha"].split("-")
        textos = {"tecnología": f["tecnologia"], "región": f["region"], "titular": f["titular"],
                  "nombre": f["nombre"], "fecha": d + m + a}  # «19/08/2026» y «19-08- 2026» quedan «19082026»
        for campo, valor in textos.items():
            if normalizar(valor) not in plano:
                faltan.append(f"{f['nombre']}: {campo} «{valor}»")
        for campo in ("potencia_mw", "inversion_musd"):
            if f[campo] is not None and como_texto(f[campo]) not in numeros:
                faltan.append(f"{f['nombre']}: {campo} {como_texto(f[campo])}")
    # los totales declarados: la cita está en la página y contiene los tres números
    if normalizar(declarado["cita"]) not in plano:
        faltan.append("la cita de los totales no está en la página")
    en_cita = numeros_en(declarado["cita"])
    for campo in ("proyectos", "mw", "mmusd"):
        if como_texto(declarado[campo]) not in en_cita:
            faltan.append(f"total {campo} {como_texto(declarado[campo])} no está en la cita")
    if faltan:
        return control("evidencia", "error", "no aparece en el texto: " + "; ".join(faltan))
    return control("evidencia", "ok", "todos los valores aparecen en la página")


# --- 4. Fecha en el mes ---------------------------------------------------------
def fecha_en_mes(filas, edicion):
    """La fecha cae en el mes que cubre el reporte (la edición de septiembre informa agosto)."""
    mes = mes_cubierto(edicion)
    fuera = [f"{f['nombre']} ({f['fecha']})" for f in filas if not f["fecha"].startswith(mes)]
    if fuera:
        return control("fecha_en_mes", "error", f"fuera de {mes}: " + "; ".join(fuera))
    return control("fecha_en_mes", "ok", f"todas las fechas caen en {mes}")


# --- 5. Unidades y rango --------------------------------------------------------
def rango(filas, minimo=0.3, maximo=3.0):
    """MW mayor que cero e inversión por MW entre 0,3 y 3 MMUSD. Es aviso: puede ser legítimo."""
    raros = []
    for f in filas:
        mw = f["potencia_mw"]
        if mw is None or f["inversion_musd"] is None:
            continue  # de eso se encarga la regla «faltante»
        if mw <= 0:
            raros.append(f"{f['nombre']}: potencia {como_texto(mw)} MW")
        elif not minimo <= f["inversion_musd"] / mw <= maximo:
            raros.append(f"{f['nombre']}: {f['inversion_musd'] / mw:.2f} MMUSD/MW".replace(".", ","))
    if raros:
        return control("rango", "aviso", "revisar: " + "; ".join(raros))
    return control("rango", "ok", "MW > 0 e inversión por MW entre 0,3 y 3 MMUSD")


# --- 6. Faltante ----------------------------------------------------------------
def faltante(filas):
    """Potencia o inversión «-» en la fuente: queda vacía (None), nunca en cero."""
    sin_dato = [f"{f['nombre']} ({campo})" for f in filas
                for campo, clave in (("potencia", "potencia_mw"), ("inversión", "inversion_musd"))
                if f[clave] is None]
    if sin_dato:
        return control("faltante", "aviso", "«-» en la fuente: " + "; ".join(sin_dato))
    return control("faltante", "ok", "todas las filas traen potencia e inversión")


# --- 7. Duplicado ---------------------------------------------------------------
def duplicado(filas, anteriores=()):
    """Mismo proyecto (nombre y titular normalizados) repetido en la misma etapa.

    Revisa dentro de la edición y contra `anteriores`: filas de ediciones previas
    de la misma etapa, cada una con su campo "edicion".
    """
    vistos = {clave(f): f["edicion"] for f in anteriores}
    repetidos = []
    for f in filas:
        k = clave(f)
        if k in vistos:
            repetidos.append(f"{f['nombre']} (ya en {vistos[k]})")
        vistos[k] = "esta edición"
    if repetidos:
        return control("duplicado", "aviso", "repetido: " + "; ".join(repetidos))
    return control("duplicado", "ok", "sin repetidos")


REGLAS = ["totales", "conteo", "evidencia", "fecha_en_mes", "rango", "faltante", "duplicado"]


def validar_edicion(edicion, extraccion, textos, anteriores=()):
    """Aplica las siete reglas a las dos tablas de una edición.

    extraccion: el último intento guardado por extraer.py
    textos:     {etapa: texto de la página}
    anteriores: filas de ediciones previas, con su "edicion" (para la regla de duplicado)
    """
    controles = []
    for etapa in ("ingreso", "aprobacion"):
        filas = [f for f in extraccion["filas"] if f["etapa"] == etapa]
        declarado = extraccion[f"declarado_{etapa}"]
        previas = [f for f in anteriores if f["etapa"] == etapa]
        for c in (totales(filas, declarado),
                  conteo(filas, declarado),
                  evidencia(filas, declarado, textos[etapa]),
                  fecha_en_mes(filas, edicion),
                  rango(filas),
                  faltante(filas),
                  duplicado(filas, previas)):
            controles.append({"edicion": edicion, "etapa": etapa, **c})
    return controles
