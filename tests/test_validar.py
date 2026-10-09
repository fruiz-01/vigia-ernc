"""Pruebas de las siete reglas y prueba de aceptación del plan."""
import copy

from conftest import cargar_referencia, cargar_textos
from vigia import validar


def fila(nombre="Parque A", titular="Titular A", fecha="2026-08-10", mw=100, inv=150, **otros):
    return {"etapa": "ingreso", "tecnologia": "Solar - PV", "region": "V", "titular": titular,
            "nombre": nombre, "fecha": fecha, "potencia_mw": mw, "inversion_musd": inv,
            "almacenamiento": True, **otros}


def declarado(proyectos, mw, mmusd, cita=""):
    return {"proyectos": proyectos, "mw": mw, "mmusd": mmusd, "cita": cita}


# --- Prueba de aceptación (tabla del plan) ----------------------------------------

def de_etapa(ref, etapa):
    return [f for f in ref["filas"] if f["etapa"] == etapa]


def test_aceptacion_septiembre_2026_ingresos(ref_202609):
    filas = de_etapa(ref_202609, "ingreso")
    assert len(filas) == 4
    assert sum(f["potencia_mw"] or 0 for f in filas) == 245
    assert sum(f["inversion_musd"] for f in filas) == 280
    el_faro = next(f for f in filas if "El Faro" in f["nombre"])
    assert el_faro["potencia_mw"] is None


def test_aceptacion_septiembre_2026_aprobados(ref_202609):
    filas = de_etapa(ref_202609, "aprobacion")
    assert len(filas) == 8
    assert sum(f["potencia_mw"] for f in filas) == 521
    assert sum(f["inversion_musd"] for f in filas) == 854


def test_aceptacion_septiembre_2026_pasa_las_reglas(ref_202609, textos_202609):
    controles = validar.validar_edicion("202609", ref_202609, textos_202609)
    assert len(controles) == 14  # 7 reglas x 2 tablas
    errores = [c for c in controles if c["resultado"] == "error"]
    assert errores == []
    avisos = [(c["etapa"], c["regla"]) for c in controles if c["resultado"] == "aviso"]
    assert avisos == [("ingreso", "faltante")]  # El Faro sin potencia


def test_aceptacion_octubre_2025_fechas_partidas():
    """En octubre de 2025 las fechas vienen como «30-09- 2025» y deben quedar 2025-09-30."""
    ref, textos = cargar_referencia("202510"), cargar_textos("202510")
    assert "30-09- 2025" in textos["ingreso"]
    pampino = next(f for f in ref["filas"] if f["nombre"] == "Parque Fotovoltaico Pampino")
    assert pampino["fecha"] == "2025-09-30"
    controles = validar.validar_edicion("202510", ref, textos)
    assert [c for c in controles if c["resultado"] == "error"] == []


def test_octubre_2025_titular_partido_con_guion():
    """«INVERSIONES CANDE-» + «LARIA SOLAR SPA» en el PDF calza con el titular unido."""
    textos = cargar_textos("202510")
    assert "CANDE-\nLARIA" in textos["aprobacion"]
    assert validar.normalizar("INVERSIONES CANDELARIA SOLAR SPA") in validar.normalizar(textos["aprobacion"])


# --- 1. Totales ---------------------------------------------------------------------

def test_totales_ok():
    filas = [fila(mw=100, inv=150), fila(mw=None, inv=10)]
    assert validar.totales(filas, declarado(2, 100, 160))["resultado"] == "ok"


def test_totales_error_da_la_diferencia():
    c = validar.totales([fila(mw=500, inv=854)], declarado(1, 521, 854))
    assert c["resultado"] == "error"
    assert "las filas suman 500 MW y el reporte declara 521" in c["detalle"]


# --- 2. Conteo ----------------------------------------------------------------------

def test_conteo():
    assert validar.conteo([fila(), fila()], declarado(2, 0, 0))["resultado"] == "ok"
    c = validar.conteo([fila()], declarado(2, 0, 0))
    assert c["resultado"] == "error" and "hay 1 filas" in c["detalle"]


# --- 3. Evidencia -------------------------------------------------------------------

def test_evidencia_detecta_un_valor_inventado(ref_202609, textos_202609):
    ref = copy.deepcopy(ref_202609)
    filas = de_etapa(ref, "aprobacion")
    filas[0]["titular"] = "Empresa Inventada SpA"
    filas[1]["inversion_musd"] = 999
    c = validar.evidencia(filas, ref["declarado_aprobacion"], textos_202609["aprobacion"])
    assert c["resultado"] == "error"
    assert "Empresa Inventada SpA" in c["detalle"] and "999" in c["detalle"]


def test_evidencia_detecta_total_que_no_esta_en_la_cita(ref_202609, textos_202609):
    dec = dict(ref_202609["declarado_aprobacion"], mw=530)
    c = validar.evidencia(de_etapa(ref_202609, "aprobacion"), dec, textos_202609["aprobacion"])
    assert c["resultado"] == "error" and "total mw 530" in c["detalle"]


def test_normalizar_espacios_guiones_y_tildes():
    assert validar.normalizar("Solar -  PV") == validar.normalizar("Solar - PV") == "solarpv"
    assert validar.normalizar("Almacena-\nmiento") == "almacenamiento"
    assert validar.normalizar("30-09- 2025") == validar.normalizar("30/09/2025") == "30092025"
    assert validar.normalizar("Pillancó") == "pillanco"


def test_numeros_en_quita_punto_de_miles():
    assert {"1248", "574", "8"} <= validar.numeros_en("acogió 8 proyectos, 574 MW y 1.248 MMUSD")


# --- 4. Fecha en el mes -------------------------------------------------------------

def test_mes_cubierto():
    assert validar.mes_cubierto("202609") == "2026-08"
    assert validar.mes_cubierto("202601") == "2025-12"


def test_fecha_fuera_del_mes():
    assert validar.fecha_en_mes([fila(fecha="2026-08-31")], "202609")["resultado"] == "ok"
    c = validar.fecha_en_mes([fila(fecha="2026-04-15")], "202609")
    assert c["resultado"] == "error" and "2026-04-15" in c["detalle"]


# --- 5. Unidades y rango ------------------------------------------------------------

def test_rango():
    assert validar.rango([fila(mw=100, inv=150)])["resultado"] == "ok"
    assert validar.rango([fila(mw=9, inv=43)])["resultado"] == "aviso"   # 4,8 MMUSD/MW
    assert validar.rango([fila(mw=100, inv=10)])["resultado"] == "aviso"  # 0,1 MMUSD/MW
    assert validar.rango([fila(mw=0, inv=10)])["resultado"] == "aviso"
    assert validar.rango([fila(mw=None, inv=10)])["resultado"] == "ok"    # lo ve «faltante»


# --- 6. Faltante --------------------------------------------------------------------

def test_faltante():
    assert validar.faltante([fila(mw=10)])["resultado"] == "ok"
    c = validar.faltante([fila(nombre="El Faro", mw=None)])
    assert c["resultado"] == "aviso" and "El Faro" in c["detalle"]


def test_inversion_faltante_no_rompe_las_reglas():
    # diciembre de 2025 trae una inversión «-»: queda en None, avisa y no cuenta en la suma
    filas = [fila(nombre="SLK", mw=9, inv=None), fila(mw=10, inv=12)]
    assert validar.faltante(filas)["resultado"] == "aviso"
    assert "SLK (inversión)" in validar.faltante(filas)["detalle"]
    assert validar.rango(filas)["resultado"] == "ok"
    assert validar.totales(filas, declarado(2, 19, 12))["resultado"] == "ok"


# --- 7. Duplicado -------------------------------------------------------------------

def test_duplicado_en_la_misma_edicion():
    c = validar.duplicado([fila(), fila(nombre="PARQUE  a", titular="titular a")])
    assert c["resultado"] == "aviso"


def test_duplicado_contra_ediciones_previas():
    previa = fila(nombre="Parque Eólico Las Lilas", titular="Parque Eólico Las Lilas SpA", edicion="202606")
    actual = fila(nombre="Parque Eólico Las Lilas", titular="Parque Eólico Las Lilas SpA")
    c = validar.duplicado([actual], [previa])
    assert c["resultado"] == "aviso" and "ya en 202606" in c["detalle"]
    assert validar.duplicado([fila(nombre="Otro")], [previa])["resultado"] == "ok"


# --- Precisión contra la referencia -------------------------------------------------

def test_precision_contra_referencia(ref_202609):
    from vigia.precision import comparar
    filas = ref_202609["filas"]
    assert comparar(filas, filas) == (96, 96, [])  # 12 filas x 8 campos
    con_errores = copy.deepcopy(filas[1:])          # omite Viena y cambia una fecha
    con_errores[0]["fecha"] = "2026-08-12"
    aciertos, total, dif = comparar(con_errores, filas)
    assert (aciertos, total) == (87, 96)
    assert any("omitió" in d for d in dif) and any("fecha" in d for d in dif)
