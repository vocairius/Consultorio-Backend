"""
Puente WebSocket entre el backend de VetVoz (Python) y Unity.

Reemplaza la idea original de "emitir estados de app" para la camilla:
en vez de resultados de consulta de fármacos, ahora se transmiten
comandos de movimiento. Se arranca en un hilo aparte para no bloquear
el loop síncrono de voz en main.py (STT/NLU siguen corriendo igual
que antes).

Instalar: pip install fastapi uvicorn websockets
"""

import asyncio
import json
import threading

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()
_clientes: set[WebSocket] = set()
_loop: asyncio.AbstractEventLoop | None = None


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clientes.add(websocket)
    print(f"Unity conectado. Clientes activos: {len(_clientes)}")
    try:
        while True:
            # Por ahora no esperamos nada de Unity, solo mantenemos la conexión viva.
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clientes.discard(websocket)
        print(f"Unity desconectado. Clientes activos: {len(_clientes)}")


async def _enviar_a_todos(mensaje: dict):
    datos = json.dumps(mensaje)
    desconectados = []
    for cliente in _clientes:
        try:
            await cliente.send_text(datos)
        except Exception:
            desconectados.append(cliente)
    for c in desconectados:
        _clientes.discard(c)


def enviar_comando(tipo: str, valor: float, relativo: bool, es_natural: bool = False):
    """Llamar desde el hilo principal (el loop síncrono de voz en main.py)
    para mandar un comando a todos los Unity conectados."""
    mensaje = {"tipo": tipo, "valor": valor, "relativo": relativo, "esNatural": es_natural}
    if _loop is None:
        print("Servidor WebSocket aún no está listo, se descarta el comando")
        return
    asyncio.run_coroutine_threadsafe(_enviar_a_todos(mensaje), _loop)


def hay_clientes_conectados() -> bool:
    """Para que quien use el puente (pipeline_voz.py, una prueba, etc.)
    pueda esperar a que Unity esté conectado antes de mandar el primer
    comando, en vez de adivinar un tiempo de espera fijo."""
    return len(_clientes) > 0


def iniciar_servidor(host: str = "0.0.0.0", port: int = 8000) -> threading.Thread:
    """Arranca el servidor FastAPI en un hilo aparte, sin bloquear main.py.
    Llamar una sola vez al inicio del programa."""
    global _loop

    def _run():
        global _loop
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
        config = uvicorn.Config(app, host=host, port=port, loop="asyncio", log_level="warning")
        server = uvicorn.Server(config)
        _loop.run_until_complete(server.serve())

    hilo = threading.Thread(target=_run, daemon=True)
    hilo.start()
    return hilo