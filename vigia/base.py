"""Base SQLite: reportes, páginas, filas, controles y la vista de proyectos."""
import sqlite3
from pathlib import Path

from vigia.validar import clave

RUTA = Path("datos/vigia.sqlite")

ESQUEMA = """
CREATE TABLE IF NOT EXISTS reportes (
    edicion    TEXT PRIMARY KEY,          -- AAAAMM
    url        TEXT,
    sha256     TEXT,
    descargado TEXT,
    estado     TEXT                       -- ok | faltante
);
CREATE TABLE IF NOT EXISTS paginas (       -- texto fuente, una vez por página
    edicion TEXT,
    etapa   TEXT,                          -- ingreso | aprobacion
    pagina  INTEGER,
    texto   TEXT,
    PRIMARY KEY (edicion, etapa)
);
CREATE TABLE IF NOT EXISTS filas (
    edicion        TEXT,
    etapa          TEXT,                   -- ingreso | aprobacion
    tecnologia     TEXT,
    region         TEXT,
    titular        TEXT,
    nombre         TEXT,
    fecha          TEXT,                   -- AAAA-MM-DD
    potencia_mw    REAL,                   -- NULL si la fuente trae «-»
    inversion_musd REAL,
    almacenamiento INTEGER,                -- 0 | 1
    pagina         INTEGER,
    clave          TEXT                    -- nombre|titular normalizados
);
CREATE TABLE IF NOT EXISTS controles (
    edicion   TEXT,
    etapa     TEXT,
    regla     TEXT,
    resultado TEXT,                        -- ok | aviso | error
    detalle   TEXT
);
CREATE VIEW IF NOT EXISTS proyectos AS     -- un proyecto puede aparecer en varias ediciones y etapas
    SELECT clave,
           MAX(nombre)  AS nombre,
           MAX(titular) AS titular,
           MAX(tecnologia) AS tecnologia,
           MAX(region)  AS region,
           MAX(CASE WHEN etapa = 'ingreso'    THEN fecha END) AS fecha_ingreso,
           MAX(CASE WHEN etapa = 'aprobacion' THEN fecha END) AS fecha_aprobacion,
           MAX(potencia_mw)    AS potencia_mw,
           MAX(inversion_musd) AS inversion_musd,
           MAX(almacenamiento) AS almacenamiento,
           GROUP_CONCAT(edicion || ' ' || etapa, '; ') AS apariciones
    FROM filas
    GROUP BY clave;
"""


def conectar(ruta=RUTA):
    if str(ruta) != ":memory:":
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(ruta)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def guardar_reportes(con, registros):
    con.executemany(
        "INSERT OR REPLACE INTO reportes VALUES (:edicion, :url, :sha256, :descargado, :estado)", registros)
    con.commit()


def guardar_edicion(con, edicion, paginas, filas, controles):
    """Reemplaza todo lo de una edición: así correr dos veces no duplica filas."""
    for tabla in ("paginas", "filas", "controles"):
        con.execute(f"DELETE FROM {tabla} WHERE edicion = ?", (edicion,))
    con.executemany("INSERT INTO paginas VALUES (?, ?, ?, ?)",
                    [(edicion, etapa, p["pagina"], p["texto"]) for etapa, p in paginas.items()])
    con.executemany(
        "INSERT INTO filas VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(edicion, f["etapa"], f["tecnologia"], f["region"], f["titular"], f["nombre"], f["fecha"],
          f["potencia_mw"], f["inversion_musd"], int(f["almacenamiento"]),
          paginas[f["etapa"]]["pagina"], clave(f)) for f in filas])
    con.executemany("INSERT INTO controles VALUES (:edicion, :etapa, :regla, :resultado, :detalle)", controles)
    con.commit()


def filas_previas(con, edicion):
    """Filas de ediciones anteriores, para la regla de duplicado."""
    cursor = con.execute("SELECT * FROM filas WHERE edicion < ?", (edicion,))
    return [dict(f) for f in cursor]
