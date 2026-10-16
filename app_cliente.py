"""Punto de entrada del cliente. Usa prompt_toolkit para no interrumpir la escritura."""

import argparse
import logging

from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout

from chat.cliente import ClienteChat
from chat.protocolo import validar_alias
from chat.registros import configurar_logs


def main() -> None:
    parser = argparse.ArgumentParser(description="Cliente del chat multiusuario LAN")
    parser.add_argument("--host", default="127.0.0.1", help="IP real del equipo servidor en la LAN")
    parser.add_argument("--puerto", type=int, default=8080, help="Puerto TCP del servidor")
    argumentos = parser.parse_args()

    configurar_logs("cliente")
    sesion = PromptSession()
    try:
        alias = validar_alias(sesion.prompt("Tu nombre para el chat: "))
    except (ValueError, KeyboardInterrupt, EOFError) as error:
        print(f"No se inició el chat: {error}")
        return

    cliente = ClienteChat(argumentos.host, argumentos.puerto)
    try:
        cliente.conectar(alias)
        print("Conectado. Escribe y presiona Enter. Para salir: /salir")
        # patch_stdout hace que mensajes impresos desde el hilo de escucha
        # no borren la línea de texto que el usuario está escribiendo.
        with patch_stdout():
            while cliente.esta_activo():
                try:
                    texto = sesion.prompt("Tú > ")
                except (EOFError, KeyboardInterrupt):
                    break
                if texto.strip().lower() == "/salir":
                    break
                if not texto.strip():
                    continue
                try:
                    cliente.enviar(texto)
                except ValueError as error:
                    print(f"[AVISO] {error}")
                except OSError as error:
                    print(f"[ERROR] Se perdió la conexión: {error}")
                    break
                except ConnectionError as error:
                    print(f"[ERROR] {error}")
                    break
    except (OSError, ConnectionError) as error:
        logging.getLogger(__name__).error("No fue posible conectarse: %s", error)
        print("Comprueba la IP, el puerto, el firewall y que el servidor esté iniciado.")
    finally:
        cliente.desconectar()
        print("Chat finalizado.")


if __name__ == "__main__":
    main()
