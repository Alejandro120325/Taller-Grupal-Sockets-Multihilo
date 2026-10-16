"""Servidor TCP concurrente: conexiones, usuarios y difusión en LAN.

Responsabilidades separadas: RegistroClientes guarda las sesiones,
GestorChat realiza la difusión y ServidorChat acepta conexiones de red.
"""

import logging
import socket
import threading
from dataclasses import dataclass, field

from chat.formato import FormateadorMensaje
from chat.protocolo import codificar_evento, leer_evento, validar_alias, validar_texto

REGISTRO = logging.getLogger(__name__)


@dataclass(eq=False)
class SesionCliente:
    """Representa una conexión activa y sincroniza los envíos al socket."""

    conexion: socket.socket
    direccion: tuple
    alias: str
    candado_envio: threading.Lock = field(default_factory=threading.Lock)

    def enviar(self, paquete: bytes) -> None:
        """Impide mezclar bytes cuando varios hilos escriben al mismo cliente."""
        with self.candado_envio:
            self.conexion.sendall(paquete)

    def cerrar(self) -> None:
        """Interrumpe la conexión de una sesión que ya no responde."""
        try:
            self.conexion.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.conexion.close()
        except OSError:
            pass


class RegistroClientes:
    """Gestiona de manera segura el conjunto de usuarios conectados."""

    def __init__(self) -> None:
        self._sesiones: dict[socket.socket, SesionCliente] = {}
        self._candado = threading.Lock()

    def registrar(self, sesion: SesionCliente) -> None:
        with self._candado:
            if any(otra.alias.casefold() == sesion.alias.casefold() for otra in self._sesiones.values()):
                raise ValueError("Ese alias ya está conectado. Escoge otro.")
            self._sesiones[sesion.conexion] = sesion

    def quitar(self, sesion: SesionCliente) -> bool:
        with self._candado:
            return self._sesiones.pop(sesion.conexion, None) is not None

    def obtener_todos(self) -> list[SesionCliente]:
        with self._candado:
            return list(self._sesiones.values())


class GestorChat:
    """Coordina mensajes sin controlar los sockets de escucha."""

    def __init__(self, registro: RegistroClientes, formateador: FormateadorMensaje) -> None:
        self._registro = registro
        self._formateador = formateador

    @property
    def registro(self) -> RegistroClientes:
        return self._registro

    def difundir(self, tipo: str, contenido: str) -> None:
        """Distribuye el evento a todos los clientes activos, incluido el emisor."""
        paquete = codificar_evento(tipo, contenido=contenido)
        for sesion in self._registro.obtener_todos():
            try:
                sesion.enviar(paquete)
            except OSError as error:
                REGISTRO.warning("Falló el envío a %s: %s", sesion.alias, error)
                # La lectura del hilo correspondiente terminará tras cerrar el socket.
                sesion.cerrar()

    def publicar_mensaje(self, alias: str, texto: str) -> None:
        contenido = self._formateador.formatear(alias, texto)
        self.difundir("mensaje", contenido)
        REGISTRO.info("Mensaje difundido | emisor=%s | longitud=%s", alias, len(texto))


class AtendedorCliente:
    """Se ocupa del ciclo de vida de un cliente particular."""

    def __init__(self, gestor: GestorChat) -> None:
        self._gestor = gestor

    def atender(self, conexion: socket.socket, direccion: tuple) -> None:
        sesion: SesionCliente | None = None
        REGISTRO.info("Conexión TCP desde %s:%s", *direccion[:2])
        try:
            with conexion, conexion.makefile("r", encoding="utf-8") as flujo:
                ingreso = leer_evento(flujo)
                if ingreso is None or ingreso.get("tipo") != "ingreso":
                    raise ValueError("El primer evento debe indicar el alias del usuario.")
                try:
                    alias = validar_alias(ingreso.get("alias"))
                    sesion = SesionCliente(conexion, direccion, alias)
                    self._gestor.registro.registrar(sesion)
                except ValueError as error:
                    # Enviamos el motivo al cliente antes de cerrar el socket.
                    conexion.sendall(codificar_evento("error", contenido=str(error)))
                    sesion = None
                    raise
                REGISTRO.info("Ingresó al chat | usuario=%s | ip=%s | puerto=%s", alias, *direccion[:2])
                self._gestor.difundir("sistema", f"{alias} se conectó al chat.")

                while True:
                    evento = leer_evento(flujo)
                    if evento is None or evento["tipo"] == "salida":
                        break
                    if evento["tipo"] != "mensaje":
                        raise ValueError("Tipo de evento inesperado.")
                    texto = validar_texto(evento.get("texto"))
                    self._gestor.publicar_mensaje(alias, texto)
        except (OSError, UnicodeError, ValueError) as error:
            REGISTRO.warning("Conexión %s:%s finalizó con aviso: %s", *direccion[:2], error)
        except Exception:
            REGISTRO.exception("Error inesperado con %s:%s", *direccion[:2])
        finally:
            if sesion is not None and self._gestor.registro.quitar(sesion):
                REGISTRO.info("Salió del chat | usuario=%s | ip=%s | puerto=%s", sesion.alias, *direccion[:2])
                self._gestor.difundir("sistema", f"{sesion.alias} salió del chat.")
            try:
                conexion.close()
            except OSError:
                pass


class ServidorChat:
    """Únicamente abre el puerto TCP y distribuye las conexiones entre hilos."""

    def __init__(self, host: str, puerto: int, gestor: GestorChat) -> None:
        self._host = host
        self._puerto = puerto
        self._atendedor = AtendedorCliente(gestor)

    def iniciar(self) -> None:
        """Acepta clientes hasta que se interrumpa el proceso con Ctrl+C."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
            servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            servidor.bind((self._host, self._puerto))
            servidor.listen(20)
            REGISTRO.info("Servidor de chat activo en %s:%s", self._host, self._puerto)
            try:
                while True:
                    conexion, direccion = servidor.accept()
                    hilo = threading.Thread(
                        target=self._atendedor.atender,
                        args=(conexion, direccion),
                        name=f"cliente-{direccion[0]}-{direccion[1]}",
                        daemon=True,
                    )
                    hilo.start()
            except KeyboardInterrupt:
                REGISTRO.info("Servidor detenido mediante Ctrl+C.")
