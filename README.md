# Consultorio con Voz

Asistente de voz manos libres que controla, por comandos hablados, la
camilla de un quirofano simulado en Unity. Proyecto de la materia
Integracion 3D (USB Cali). Sucesor de VetVoz/VetVoice, que originalmente
hacia consulta de dosis farmacologicas; el profesor pidio integrar ese
trabajo con una simulacion Unity de quirofano, moviendo una camilla por voz.

## Como funciona

1. `pipeline_voz.py` transcribe la instruccion hablada (por ahora, un stub
   de prueba — el STT real aun no esta conectado).
2. Le pide al LLM (Nemotron via OpenRouter) que interprete el texto como
   un comando de camilla: tipo, valor, si es relativo y si fue una
   peticion vaga ("natural").
3. `servidor.py` levanta un puente WebSocket (FastAPI) que manda ese
   comando a Unity.
4. En Unity, `UnityWebSocketClient.cs` recibe el comando y llama a
   `CamillaController.cs`, que mueve la pieza correspondiente con una
   animacion suave.
5. `pipeline_voz.py` confirma por voz (edge-tts) lo que se hizo, o pide
   que se repita si no entendio el comando.

Los scripts de Unity (`CamillaController.cs`, `UnityWebSocketClient.cs`)
viven en el proyecto de Unity, no en este repo.

## Instalacion

```bash
uv sync
cp .env.example .env   # y pon ahi tu OPENROUTER_API_KEY
```

## Probar el puente sin voz

Con Unity en Play y `UnityWebSocketClient` conectado:

```bash
uv run Pruebas/prueba_servidor.py
```

## Correr el pipeline completo

```bash
uv run pipeline_voz.py
```
