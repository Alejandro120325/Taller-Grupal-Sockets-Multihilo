"""Contrato de comunicación entre el servidor y los clientes.

Cada evento viaja como un objeto JSON codificado en UTF-8 y terminado en '\\n'.
El salto de línea permite distinguir mensajes aunque TCP junte varios paquetes.

Cliente -> servidor: ingreso (alias), mensaje (texto) y salida.
Servidor -> cliente: mensaje, sistema y error (todos con contenido).
"""

import json
import re
from typing import Any, TextIO

# El límite de red incluye el JSON, los campos y el salto de línea final.
MAX_EVENTO_BYTES = 4096
# Estos dos límites cuentan caracteres del texto, no bytes UTF-8.
MAX_TEXTO = 500
MAX_ALIAS = 20
PATRON_ALIAS = re.compile(r"^[\w -]+$", re.UNICODE)
# \w admite letras Unicode, números y guion bajo; se añaden espacio y guion.


def validar_alias(alias: str) -> str:
    """Valida y normaliza el nombre visible de una persona."""
    if not isinstance(alias, str):
        raise ValueError("El alias debe ser texto.")
    alias = alias.strip()
    # Se eliminan los espacios exteriores; los interiores forman parte del nombre.
    if not 1 <= len(alias) <= MAX_ALIAS or not PATRON_ALIAS.fullmatch(alias):
        raise ValueError("Alias inválido: usa 1 a 20 caracteres (letras, números, espacios, - o _).")
    return alias


def validar_texto(texto: str) -> str:
    """Comprueba que el mensaje no esté vacío ni exceda el límite."""
    if not isinstance(texto, str):
        raise ValueError("El mensaje debe ser texto.")
    texto = texto.strip()
    if not 1 <= len(texto) <= MAX_TEXTO:
        raise ValueError("Escribe un mensaje de entre 1 y 500 caracteres.")
    return texto


def codificar_evento(tipo: str, **datos: Any) -> bytes:
    """Convierte un evento en una línea JSON lista para enviarse por TCP."""
    evento = {"tipo": tipo, **datos}
    # Conservamos tildes y eñes; los separadores compactos reducen el tamaño.
    # El salto final delimita el evento porque TCP transporta un flujo de bytes.
    paquete = (json.dumps(evento, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    if len(paquete) > MAX_EVENTO_BYTES:
        raise ValueError("El evento supera el tamaño máximo permitido.")
    return paquete


def leer_evento(flujo: TextIO) -> dict[str, Any] | None:
    """Lee exactamente un evento; retorna None si se cierra la conexión.

    La lectura tiene límite para evitar consumir memoria sin control.
    """
    linea = flujo.readline(MAX_EVENTO_BYTES + 1)
    # TextIO limita caracteres. La comprobación posterior mide bytes porque
    # un carácter Unicode puede ocupar varios bytes al codificarse en UTF-8.
    if not linea:
        return None
    if not linea.endswith("\n") or len(linea.encode("utf-8")) > MAX_EVENTO_BYTES:
        raise ValueError("Evento demasiado largo o sin terminador de línea.")
    try:
        evento = json.loads(linea)
    except json.JSONDecodeError as error:
        raise ValueError("El evento recibido no contiene JSON válido.") from error
    if not isinstance(evento, dict) or not isinstance(evento.get("tipo"), str):
        raise ValueError("El evento recibido no tiene un tipo válido.")
    # Los campos propios de cada tipo se validan donde se procesa el evento.
    return evento
