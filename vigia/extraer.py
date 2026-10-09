"""Lee las tablas con un modelo de lenguaje y guarda la respuesta en caché.

El modelo recibe el texto de las dos páginas y devuelve un JSON con forma fija
(esquema Pydantic). Si las filas no cuadran con los totales o el conteo que el
propio reporte declara, se le devuelve la diferencia concreta y se reintenta una
sola vez. Cada respuesta queda en datos/extracciones/AAAAMM.json: con la caché,
volver a validar no necesita clave ni cuesta nada.

Para llamar al modelo hace falta la variable de entorno ANTHROPIC_API_KEY.
Sin ella, `python -m vigia extraer` solo usa las extracciones ya guardadas.
"""
import json
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from vigia import validar

CARPETA = Path("datos/extracciones")
MODELO = "claude-opus-5-5"


# --- Esquema de la respuesta ------------------------------------------------

class Fila(BaseModel):
    etapa: Literal["ingreso", "aprobacion"]
    tecnologia: str = Field(description="Tal como aparece, p. ej. 'Eólica' o 'Solar - PV'")
    region: str = Field(description="Número romano, 'RM' o 'Interregional'")
    titular: str
    nombre: str
    fecha: date = Field(description="Fecha de ingreso o aprobación, en formato AAAA-MM-DD")
    potencia_mw: float | None = Field(description="null si la celda trae '-'")
    inversion_musd: float | None = Field(description="null si la celda trae '-'")
    almacenamiento: bool = Field(description="true si la columna dice 'Si'")


class Declarado(BaseModel):
    """Totales que el texto del reporte declara para una tabla."""
    proyectos: int
    mw: float
    mmusd: float
    cita: str = Field(description="Frase textual del reporte de donde salen los tres números")


class Extraccion(BaseModel):
    filas: list[Fila]
    declarado_ingreso: Declarado
    declarado_aprobacion: Declarado


INSTRUCCIONES = """Eres un asistente que transcribe tablas del Reporte Mensual ERNC de la Comisión Nacional de Energía de Chile.

Abajo va el texto de dos páginas extraído de un PDF. Cada página trae una tabla:
- «Proyectos Ingresados a Evaluación Ambiental» (etapa "ingreso")
- «Proyectos con RCA Aprobada» (etapa "aprobacion")

El texto viene desordenado: cada celda está en su propia línea, y los nombres y titulares largos
están partidos en varias líneas, a veces con guion de corte («CANDE-» + «LARIA» = «CANDELARIA»).
Columnas de cada fila: Tecnología, Región, Titular, Nombre, Fecha, Potencia [MW], Inversión [MMUSD],
WEB («Ver», se ignora) y Almacenamiento («Si»/«No»).

Reglas:
1. Una fila por proyecto de cada tabla, sin omitir ni inventar ninguna.
2. Copia titular y nombre tal como están, uniendo las líneas partidas y quitando el guion de corte.
3. Fechas en formato AAAA-MM-DD, vengan como «19/08/2026» o «30-09- 2025».
4. Si la potencia o la inversión es «-», devuelve null (no 0).
5. Los números usan punto de miles: «1.248» es 1248.
6. Para cada tabla, el párrafo de arriba declara cuántos proyectos hubo y cuántos MW y MMUSD suman.
   Devuelve esos tres números y la frase textual de donde salen. No los calcules tú.
"""


def armar_mensaje(paginas):
    """Texto del mensaje: instrucciones más el texto de cada página."""
    partes = [INSTRUCCIONES]
    for etapa, p in paginas.items():
        partes.append(f"\n=== Página {p['pagina']} (tabla de {etapa}) ===\n{p['texto']}")
    return "\n".join(partes)


def llamar_modelo(cliente, mensajes):
    """Una llamada a la API. Devuelve una Extraccion o lanza error si no sirve."""
    respuesta = cliente.messages.parse(
        model=MODELO,
        max_tokens=16000,
        messages=mensajes,
        output_format=Extraccion,
        output_config={"effort": "low"},
    )
    # Antes de leer la respuesta: ¿terminó bien?
    if respuesta.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"El modelo no completó la respuesta (stop_reason={respuesta.stop_reason})")
    if respuesta.parsed_output is None:
        raise RuntimeError("La respuesta no trae una extracción válida")
    return respuesta.parsed_output


def diferencias(extraccion):
    """Fallas de las reglas que gatillan reintento (totales y conteo), en texto."""
    datos = extraccion.model_dump(mode="json")
    fallas = []
    for etapa in ("ingreso", "aprobacion"):
        filas = [f for f in datos["filas"] if f["etapa"] == etapa]
        declarado = datos[f"declarado_{etapa}"]
        for control in (validar.totales(filas, declarado), validar.conteo(filas, declarado)):
            if control["resultado"] == "error":
                fallas.append(f"Tabla de {etapa}: {control['detalle']}")
    return fallas


def extraer_edicion(edicion, paginas, cliente, carpeta=CARPETA):
    """Extrae una edición, con un reintento si no cuadra. Usa la caché si existe."""
    ruta = carpeta / f"{edicion}.json"
    if ruta.exists():
        return json.loads(ruta.read_text(encoding="utf-8"))

    mensajes = [{"role": "user", "content": armar_mensaje(paginas)}]
    intentos = [llamar_modelo(cliente, mensajes)]

    fallas = diferencias(intentos[0])
    if fallas:  # un solo reintento, entregando la diferencia concreta
        print(f"  {edicion}: reintento por {len(fallas)} diferencia(s)")
        mensajes += [
            {"role": "assistant", "content": intentos[0].model_dump_json()},
            {"role": "user", "content": "Tu extracción no cuadra con lo que declara el reporte:\n- "
             + "\n- ".join(fallas)
             + "\nRevisa el texto de nuevo y devuelve la extracción completa corregida."},
        ]
        intentos.append(llamar_modelo(cliente, mensajes))

    resultado = {
        "edicion": edicion,
        "modelo": MODELO,
        "paginas": {etapa: p["pagina"] for etapa, p in paginas.items()},
        # se guardan todos los intentos; el último es el que vale
        "intentos": [i.model_dump(mode="json") for i in intentos],
    }
    carpeta.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    return resultado
