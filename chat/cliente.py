"""Cliente concurrente: el usuario escribe mientras otro hilo recibe mensajes."""

import logging
import socket
import threading

from chat.protocolo import codificar_evento, leer_evento, validar_alias, validar_texto

REGISTRO = logging.getLogger(__name__)


class ClienteChat:
    """Conecta con el servidor, emite eventos y escucha sin bloquear el teclado."""

    def __init__(self, host: str, puerto: int) -> None:
        self._host = host
        self._puerto = puerto
        self._conexion: socket.socket | None = None
        self._activo = threading.Event()
        self._hilo_escucha: threading.Thread | None = None

    def conectar(self, alias: str) -> None:
        alias = validar_alias(alias)
        self._conexion = socket.create_connection((self._host, self._puerto), timeout=10)
        self._conexion.settimeout(None)
        self._activo.set()
        self._conexion.sendall(codificar_evento("ingreso", alias=alias))
        REGISTRO.info("Conectado al servidor %s:%s como %s", self._host, self._puerto, alias)
        self._hilo_escucha = threading.Thread(
            target=self._escuchar, name="escucha-mensajes", daemon=True
        )
        self._hilo_escucha.start()

    def _escuchar(self) -> None:
        assert self._conexion is not None
        try:
            with self._conexion.makefile("r", encoding="utf-8") as flujo:
                while self._activo.is_set():
                    evento = leer_evento(flujo)
                    if evento is None:
                        print("\n[INFO] El servidor cerró la conexión.")
                        break
                    if evento["tipo"] == "error":
                        print(f"\n[ERROR] {evento.get('contenido', 'Solicitud rechazada')}")
                        break
                    if evento["tipo"] in {"mensaje", "sistema"}:
                        print(f"\n{evento.get('contenido', '')}")
        except (OSError, UnicodeError, ValueError) as error:
            if self._activo.is_set():
                REGISTRO.warning("Se interrumpió la lectura: %s", error)
                print("\n[INFO] Se perdió la conexión.")
        finally:
            self._activo.clear()
            REGISTRO.info("Hilo de recepción terminado.")

    def enviar(self, texto: str) -> None:
        if not self._activo.is_set() or self._conexion is None:
            raise ConnectionError("No hay conexión activa con el servidor.")
        texto = validar_texto(texto)
        self._conexion.sendall(codificar_evento("mensaje", texto=texto))
        REGISTRO.info("Mensaje enviado | longitud=%s", len(texto))

    def esta_activo(self) -> bool:
        return self._activo.is_set()

    def desconectar(self) -> None:
        if self._conexion is None:
            return
        if self._activo.is_set():
            try:
                self._conexion.sendall(codificar_evento("salida"))
            except OSError:
                pass
        self._activo.clear()
        try:
            self._conexion.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self._conexion.close()
        REGISTRO.info("Conexión local cerrada.")
