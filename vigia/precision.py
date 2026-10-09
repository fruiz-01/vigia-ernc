"""Compara lo que extrajo el modelo con una referencia transcrita a mano, campo por campo."""
from vigia.validar import normalizar

CAMPOS = ["tecnologia", "region", "titular", "nombre", "fecha",
          "potencia_mw", "inversion_musd", "almacenamiento"]


def igual(a, b):
    """Textos se comparan normalizados (espacios, guiones, tildes); el resto, tal cual."""
    if isinstance(a, str) and isinstance(b, str):
        return normalizar(a) == normalizar(b)
    return a == b


def comparar(extraidas, referencia):
    """Devuelve (aciertos, total, diferencias). Las filas se emparejan por etapa y nombre.

    Una fila de la referencia que el modelo omitió cuenta todos sus campos como errores.
    """
    por_nombre = {(f["etapa"], normalizar(f["nombre"])): f for f in extraidas}
    aciertos, total, emparejadas, diferencias = 0, 0, 0, []
    for ref in referencia:
        fila = por_nombre.get((ref["etapa"], normalizar(ref["nombre"])))
        if fila is None:
            total += len(CAMPOS)
            diferencias.append(f"{ref['nombre']}: el modelo omitió la fila")
            continue
        emparejadas += 1
        for campo in CAMPOS:
            total += 1
            if igual(fila[campo], ref[campo]):
                aciertos += 1
            else:
                diferencias.append(f"{ref['nombre']} · {campo}: modelo {fila[campo]!r}, referencia {ref[campo]!r}")
    if len(extraidas) > emparejadas:
        diferencias.append(f"{len(extraidas) - emparejadas} fila(s) extraída(s) que no están en la referencia")
    return aciertos, total, diferencias
