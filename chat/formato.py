"""Presentación de mensajes separada de la comunicación por red (SOLID)."""

from abc import ABC, abstractmethod


class FormateadorMensaje(ABC):
    """Contrato que permite cambiar el formato sin modificar el servidor."""

    @abstractmethod
    def formatear(self, alias: str, texto: str) -> str:
        """Devuelve la representación visible de un mensaje de chat."""
        # Las implementaciones concretas deben definir este método.


class FormateadorConsola(FormateadorMensaje):
    """Presentación simple de una conversación por consola."""

    def formatear(self, alias: str, texto: str) -> str:
        """Antecede el texto con el nombre de quien lo envía."""
        return f"[{alias}]: {texto}"
