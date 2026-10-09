"""Hallazgos de la fuente, explicados por el autor tras revisar cada error a mano.

Las reglas marcan; estas notas explican por qué. Se muestran en el informe y en
el Verificador del escritorio junto a la edición que corresponde.
"""

NOTAS = {
    "202604": "Errata en el PDF: el texto declara «3 13 MW». El modelo leyó 313, que es lo que suman las filas "
              "(172 + 128 + 13), pero la regla de evidencia busca el número escrito tal cual y no lo encuentra. "
              "Es un falso positivo y se deja a la vista.",
    "202606": "La edición de junio repite las tablas de abril: las fechas son de abril aunque debería informar mayo, "
              "por eso falla la regla de fecha. La fuente no tiene tablas de mayo. Además, «Parque Eólico Las Lilas» "
              "figura como Solar - PV en el PDF y se transcribe tal cual.",
    "202607": "Repite otra vez las tablas de abril, ya vistas en junio: falla la fecha y la regla de duplicado "
              "marca las cuatro filas.",
}

# Nombre de cada regla y de cada tabla tal como se muestra a una persona
NOMBRE_REGLA = {"totales": "Totales", "conteo": "Conteo", "evidencia": "Evidencia", "fecha_en_mes": "Fecha",
                "rango": "Rango", "faltante": "Faltante", "duplicado": "Duplicado"}
NOMBRE_ETAPA = {"ingreso": "Ingresos", "aprobacion": "Aprobados"}
