"""Pruebas unitarias y de integración mediante sockets reales en localhost."""

import io
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

from chat.formato import FormateadorConsola
from chat.protocolo import codificar_evento, leer_evento, validar_alias, validar_texto

RAIZ = Path(__file__).resolve().parent.parent


class PruebasUnitarias(unittest.TestCase):
    """Verifica formato y protocolo sin iniciar un servidor."""

    def test_formato(self):
        """Comprueba la representación que verán los usuarios."""
        self.assertEqual(FormateadorConsola().formatear("Ana", "Hola"), "[Ana]: Hola")

    def test_dos_eventos_consecutivos_en_tcp(self):
        """Comprueba que dos eventos juntos se puedan leer por separado."""
        # StringIO simula el lector de texto del socket con dos líneas seguidas.
        contenido = codificar_evento("mensaje", texto="uno") + codificar_evento("mensaje", texto="dos")
        flujo = io.StringIO(contenido.decode("utf-8"))
        self.assertEqual(leer_evento(flujo)["texto"], "uno")
        self.assertEqual(leer_evento(flujo)["texto"], "dos")

    def test_validacion(self):
        """Comprueba la limpieza de espacios y el rechazo de entradas inválidas."""
        self.assertEqual(validar_alias("  Ana  "), "Ana")
        self.assertEqual(validar_texto(" Hola "), "Hola")
        with self.assertRaises(ValueError):
            validar_alias("nombre_con_mas_de_20_caracteres")
        with self.assertRaises(ValueError):
            validar_texto(" ")


class PruebasIntegracion(unittest.TestCase):
    """Ejercita el servidor real con clientes TCP creados por las pruebas."""

    @classmethod
    def setUpClass(cls):
        """Inicia un servidor compartido por los casos de esta clase."""
        with socket.socket() as temporal:
            # El puerto 0 pide al sistema uno libre; se libera antes de iniciar
            # el servidor, que intentará ocupar ese mismo número de puerto.
            temporal.bind(("127.0.0.1", 0))
            cls.puerto = temporal.getsockname()[1]
        cls.proceso = subprocess.Popen(
            [sys.executable, "app_servidor.py", "--host", "127.0.0.1", "--puerto", str(cls.puerto)],
            cwd=RAIZ,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Reintenta brevemente hasta que el proceso acepte conexiones.
        # La conexión de sondeo se cierra sin registrar ningún usuario.
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", cls.puerto), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        cls.proceso.terminate()
        raise RuntimeError("El servidor no inició para las pruebas.")

    @classmethod
    def tearDownClass(cls):
        """Detiene el proceso del servidor al finalizar la clase."""
        cls.proceso.terminate()
        try:
            cls.proceso.wait(timeout=3)
        except subprocess.TimeoutExpired:
            # Si no termina a tiempo, fuerza el cierre y recoge el proceso.
            cls.proceso.kill()
            cls.proceso.wait()

    def test_dos_usuarios_conversan_y_se_desconectan(self):
        """Verifica ingreso, difusión a ambos usuarios y salida voluntaria."""
        with socket.create_connection(("127.0.0.1", self.puerto), timeout=3) as uno, \
                socket.create_connection(("127.0.0.1", self.puerto), timeout=3) as dos:
            uno.settimeout(3)
            dos.settimeout(3)
            with uno.makefile("r", encoding="utf-8") as leer_uno, \
                    dos.makefile("r", encoding="utf-8") as leer_dos:
                uno.sendall(codificar_evento("ingreso", alias="Ana"))
                # Se consumen los avisos de ingreso antes de comprobar mensajes.
                self.assertEqual(leer_evento(leer_uno)["tipo"], "sistema")
                dos.sendall(codificar_evento("ingreso", alias="Luis"))
                self.assertIn("Luis se conectó", leer_evento(leer_uno)["contenido"])
                self.assertEqual(leer_evento(leer_dos)["tipo"], "sistema")

                uno.sendall(codificar_evento("mensaje", texto="Hola a todos"))
                # La difusión incluye al emisor, que también recibe su mensaje.
                self.assertEqual(leer_evento(leer_uno)["contenido"], "[Ana]: Hola a todos")
                self.assertEqual(leer_evento(leer_dos)["contenido"], "[Ana]: Hola a todos")

                dos.sendall(codificar_evento("mensaje", texto="Hola, Ana"))
                self.assertEqual(leer_evento(leer_uno)["contenido"], "[Luis]: Hola, Ana")
                self.assertEqual(leer_evento(leer_dos)["contenido"], "[Luis]: Hola, Ana")

                dos.sendall(codificar_evento("salida"))
                self.assertIn("Luis salió", leer_evento(leer_uno)["contenido"])
                uno.sendall(codificar_evento("salida"))

    def test_cierre_imprevisto_de_un_cliente(self):
        """Verifica que un corte de conexión no impida conversar al otro usuario."""
        with socket.create_connection(("127.0.0.1", self.puerto), timeout=3) as uno:
            uno.settimeout(3)
            with uno.makefile("r", encoding="utf-8") as lectura:
                uno.sendall(codificar_evento("ingreso", alias="Carla"))
                self.assertEqual(leer_evento(lectura)["tipo"], "sistema")
                dos = socket.create_connection(("127.0.0.1", self.puerto), timeout=3)
                dos.sendall(codificar_evento("ingreso", alias="Pedro"))
                self.assertIn("Pedro se conectó", leer_evento(lectura)["contenido"])
                dos.shutdown(socket.SHUT_RDWR)
                dos.close()  # Sin evento de salida: simula cierre imprevisto.
                self.assertIn("Pedro salió", leer_evento(lectura)["contenido"])
                uno.sendall(codificar_evento("mensaje", texto="Seguimos conectados"))
                self.assertEqual(leer_evento(lectura)["contenido"], "[Carla]: Seguimos conectados")
                uno.sendall(codificar_evento("salida"))

    def test_alias_duplicado_se_rechaza(self):
        """Comprueba que el segundo cliente reciba el motivo del rechazo."""
        with socket.create_connection(("127.0.0.1", self.puerto), timeout=3) as uno, \
                socket.create_connection(("127.0.0.1", self.puerto), timeout=3) as dos:
            uno.settimeout(3)
            dos.settimeout(3)
            with uno.makefile("r", encoding="utf-8") as lectura_uno, \
                    dos.makefile("r", encoding="utf-8") as lectura_dos:
                uno.sendall(codificar_evento("ingreso", alias="Marta"))
                self.assertEqual(leer_evento(lectura_uno)["tipo"], "sistema")
                dos.sendall(codificar_evento("ingreso", alias="Marta"))
                evento = leer_evento(lectura_dos)
                self.assertEqual(evento["tipo"], "error")
                self.assertIn("alias", evento["contenido"])
                uno.sendall(codificar_evento("salida"))


if __name__ == "__main__":
    unittest.main()
