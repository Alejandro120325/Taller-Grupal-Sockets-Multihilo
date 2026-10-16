"""Configuración uniforme de logs para el cliente y el servidor."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class ManejadorConsolaDinamico(logging.StreamHandler):
    """Envía logs al flujo actual, incluso si el prompt redirige stdout/stderr."""

    def emit(self, registro: logging.LogRecord) -> None:
        """Usa el destino de errores vigente al emitir cada registro."""
        # patch_stdout puede sustituir stderr después de crear este manejador.
        self.stream = sys.stderr
        super().emit(registro)


def configurar_logs(nombre_aplicacion: str) -> None:
    """Escribe logs en consola y archivo rotativo (máximo 1 MB por archivo)."""
    carpeta = Path(__file__).resolve().parent.parent / "logs"
    # La ruta parte del proyecto y no del directorio desde el que se ejecuta.
    carpeta.mkdir(parents=True, exist_ok=True)

    formato = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(threadName)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    raiz = logging.getLogger()
    raiz.setLevel(logging.INFO)
    # Sustituye la configuración anterior para no duplicar cada mensaje.
    raiz.handlers.clear()

    consola = ManejadorConsolaDinamico()
    consola.setFormatter(formato)
    raiz.addHandler(consola)

    archivo = RotatingFileHandler(
        carpeta / f"{nombre_aplicacion}.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    # Al alcanzar el tamaño máximo, rota el archivo y conserva hasta tres copias.
    archivo.setFormatter(formato)
    raiz.addHandler(archivo)
