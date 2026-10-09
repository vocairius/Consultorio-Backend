"""
Prueba aislada del puente WebSocket, sin STT ni NLU de por medio.
Corre esto con Unity en Play y UnityWebSocketClient ya conectado, para
confirmar que los comandos llegan y la camilla se mueve, antes de meter
la parte de voz a la ecuacion.
"""
import sys
import time
from pathlib import Path

# Para poder importar servidor.py desde la raiz del proyecto al correr
# este script dentro de Pruebas/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import servidor

servidor.iniciar_servidor()
time.sleep(1)

input(
    "Dale Play a Unity y espera a que su Console diga "
    "'Conectado al backend de voz...'. Cuando lo veas, "
    "presiona Enter aquí para mandar el comando de prueba.\n"
)

print("Enviando comando de prueba: Trendelenburg +15 grados...")
servidor.enviar_comando("trendelenburg", 15, True)

input("Revisa Unity. Presiona Enter para terminar...\n")