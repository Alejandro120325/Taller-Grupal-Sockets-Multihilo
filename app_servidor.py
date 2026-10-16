"""Punto de entrada del servidor. Uso: python app_servidor.py --host 0.0.0.0 --puerto 8080."""

import argparse
import logging

from chat.formato import FormateadorConsola
from chat.registros import configurar_logs
from chat.servidor import GestorChat, RegistroClientes, ServidorChat


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor del chat multiusuario LAN")
    parser.add_argument("--host", default="0.0.0.0", help="IP para escuchar; 0.0.0.0 habilita LAN")
    parser.add_argument("--puerto", type=int, default=8080, help="Puerto TCP (predeterminado: 8080)")
    argumentos = parser.parse_args()

    configurar_logs("servidor")
    gestor = GestorChat(RegistroClientes(), FormateadorConsola())
    try:
        ServidorChat(argumentos.host, argumentos.puerto, gestor).iniciar()
    except OSError as error:
        logging.getLogger(__name__).error("No se pudo iniciar el servidor: %s", error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
