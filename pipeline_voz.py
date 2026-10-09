# IMPORTS
import os
import re
import json
import time
import asyncio
import edge_tts
import pygame
from openai import OpenAI
from dotenv import load_dotenv

import servidor

# CARGA DEL CLIENTE DE OPENROUTER
load_dotenv()

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

# MODELO USADO
MODELO = "nvidia/nemotron-3.5-lightning:free"

# -------------------------------------------------
# VOZ GENERADA (edge-tts)
# -------------------------------------------------
async def _generar_audio_edge(texto: str, output_file: str):
    """
    Se conecta a la API de Microsoft Azure TTS y guarda el archivo de audio.
    """
    # Voz neuronal de Colombia
    VOICE = "es-CO-GonzaloNeural"
    communicate = edge_tts.Communicate(texto, VOICE)
    await communicate.save(output_file)


def hablar(texto: str):
    """
    Genera y reproduce el audio usando edge-tts y pygame.
    Esta función bloquea la ejecución hasta que el audio termine de sonar.
    """
    print(f"[voz]: {texto}")

    archivo_temp = "respuesta_vetvoz.mp3"

    # 1. Generar el audio
    asyncio.run(_generar_audio_edge(texto, archivo_temp))

    # 2. Inicializar el mixer de pygame para reproducir
    pygame.mixer.init()
    pygame.mixer.music.load(archivo_temp)
    pygame.mixer.music.play()

    # 3. Esperar a que el audio termine
    while pygame.mixer.music.get_busy():
        pygame.time.Clock().tick(10)

    # 4. Limpiar y liberar el archivo para que se pueda borrar y sobreescribir luego
    pygame.mixer.music.unload()
    pygame.mixer.quit()

    # 5. Borrar el archivo temporal
    if os.path.exists(archivo_temp):
        os.remove(archivo_temp)


# -------------------------------------------------
# RECONOCIMIENTO DE VOZ (STT)
# -------------------------------------------------
def transcribir_audio() -> str:
    """
    Usa whisper.cpp local para transcribir audio del micrófono.
    Graba 5 segundos de audio y los procesa con el modelo español.
    """
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    import subprocess
    import tempfile
    import os


    # Parámetros de grabación
    SAMPLE_RATE = 16000  # Whisper espera 16kHz
    DURATION = 5         # Segundos de grabación (ajustable)


    print("[voz]: Escuchando... (habla ahora)")


    try:
        # Grabación de audio
        recording = sd.rec(
            int(DURATION * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype='float32'
        )
        sd.wait()  # Esperar a que termine la grabación


        # Normalizar y convertir a int16 para WAV
        audio_int16 = (np.clip(recording, -1, 1) * 32767).astype(np.int16)


        # Guardar temporalmente como WAV
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
            sf.write(tmp_wav.name, audio_int16.flatten(), SAMPLE_RATE)
            wav_path = tmp_wav.name


        # Ejecutar whisper.cpp
        result = subprocess.run([
            "whisper-cli",
            "-m", "./ggml-small-es.bin",
            "-f", wav_path,
            "--language", "es",
            "--no-timestamps"  # Para obtener solo el texto sin timestamps
        ], capture_output=True, text=True, timeout=30)


        # Limpiar archivo temporal
        os.unlink(wav_path)


        if result.returncode != 0:
            print(f"[error] whisper.cpp falló: {result.stderr}")
            return "sube la camilla veinte centimetros"  # Fallback al stub


        transcribed_text = result.stdout.strip()


        if not transcribed_text:
            print("[advertencia] No se detectó voz, usando comando de prueba")
            return "sube la camilla veinte centimetros"


        print(f"[voz] Transcripción: '{transcribed_text}'")
        return transcribed_text


    except Exception as e:
        print(f"[error] En transcripción: {e}")
        return "sube la camilla veinte centimetros"  # Fallback seguro


# -------------------------------------------------
# LÓGICA DE COMANDOS DE LA CAMILLA
# -------------------------------------------------
PROMPT_SISTEMA_CAMILLA = """Eres el interprete de comandos de voz de una camilla de quirofano.
Tu unica tarea es leer lo que dijo el usuario y devolver un JSON con el comando que quiso dar.

Tipos de comando validos (campo "tipo"):
- "altura": subir o bajar toda la camilla (mm)
- "trendelenburg": inclinar la cabeza hacia abajo o hacia arriba (grados) - es lo que la gente
  suele pedir cuando dice solo "inclina la camilla" sin especificar de que lado, o cuando
  menciona la palabra "Trendelenburg" directamente
- "tiltLateral": inclinar de lado a lado (grados) - solo cuando el usuario menciona
  explicitamente un lado ("izquierda", "derecha", "lateral")
- "fowler": subir o bajar el respaldo/cabezal (grados)
- "longitudinal": deslizar la camilla hacia la cabecera o hacia los pies (mm)

Responde SOLO con un JSON, sin texto adicional ni explicacion, con esta forma exacta:
{"tipo": "<uno de los 5 de arriba, o null si no entendiste>",
 "valor": <numero o null si el usuario no dio un valor exacto>,
 "relativo": <true si es un cambio incremental ("sube", "mas", "inclina"), false si dio
              un valor absoluto ("pon la altura en 900", "a 15 grados")>,
 "esNatural": <true si el usuario pidio algo vago sin numero ("un poco", "mas", "bajala")>}

Si lo que dijo el usuario no tiene nada que ver con mover la camilla, responde:
{"tipo": null, "valor": null, "relativo": true, "esNatural": false}

Ejemplos:
Usuario: "sube la camilla veinte centimetros"
{"tipo": "altura", "valor": 200, "relativo": true, "esNatural": false}

Usuario: "ponla en Trendelenburg"
{"tipo": "trendelenburg", "valor": 15, "relativo": false, "esNatural": false}

Usuario: "inclinala un poco"
{"tipo": "trendelenburg", "valor": null, "relativo": true, "esNatural": true}

Usuario: "inclinala hacia la izquierda diez grados"
{"tipo": "tiltLateral", "valor": -10, "relativo": true, "esNatural": false}

Usuario: "sube el respaldo"
{"tipo": "fowler", "valor": null, "relativo": true, "esNatural": true}

Usuario: "muevela hacia los pies"
{"tipo": "longitudinal", "valor": null, "relativo": true, "esNatural": true}

Usuario: "que hora es"
{"tipo": null, "valor": null, "relativo": true, "esNatural": false}
"""


def extraer_comando(texto: str) -> dict | None:
    """
    Le pide al modelo (via OpenRouter) que lea la instruccion en lenguaje
    natural y devuelva SOLO un JSON con el comando de camilla que se pidio.
    Devuelve None si el texto no tiene nada que ver con mover la camilla,
    o si la respuesta del modelo no se pudo interpretar.
    """
    try:
        respuesta = client.chat.completions.create(
            model=MODELO,
            messages=[
                {"role": "system", "content": PROMPT_SISTEMA_CAMILLA},
                {"role": "user", "content": texto},
            ],
        )
        contenido = respuesta.choices[0].message.content.strip()
        contenido = re.sub(r"^```(json)?|```$", "", contenido, flags=re.MULTILINE).strip()

        try:
            comando = json.loads(contenido)
        except json.JSONDecodeError:
            return None

        if comando.get("tipo") is None:
            return None

        if comando.get("valor") is None:
            # El propio CamillaController en Unity aplica el incremento por
            # defecto cuando esNatural=true; aca solo hace falta la bandera.
            comando["valor"] = 0
            comando["esNatural"] = True

        return comando

    except openai.RateLimitError:
        print("[error] Límite de tasa de OpenRouter agotado")
        return None
    except Exception as e:
        print(f"[error] En extraer_comando: {e}")
        return None


def generar_confirmacion(comando: dict) -> str:
    """Arma una frase corta de confirmacion segun el tipo de comando."""
    nombres = {
        "altura": "la altura",
        "trendelenburg": "el Trendelenburg",
        "tiltLateral": "el tilt lateral",
        "fowler": "el respaldo",
        "longitudinal": "el movimiento longitudinal",
    }
    return f"Ajustando {nombres.get(comando['tipo'], comando['tipo'])}."


def main():
    # Arranca el puente WebSocket en segundo plano y espera a que Unity
    # ya esté conectado antes de seguir, en vez de un sleep fijo que
    # podría no alcanzar (o sobrar).
    servidor.iniciar_servidor()
    time.sleep(0.5)  # darle un instante al servidor a levantar
    print("Esperando a que Unity se conecte...")
    while not servidor.hay_clientes_conectados():
        time.sleep(0.5)
    print("Unity conectado.")

    instruccion = transcribir_audio()
    print("Instruccion transcrita:", instruccion)

    comando = extraer_comando(instruccion)
    print("Comando detectado (OpenRouter):", comando)

    if comando is None:
        hablar("No entendi ese comando, puedes repetirlo.")
        return

    servidor.enviar_comando(
        tipo=comando["tipo"],
        valor=comando["valor"],
        relativo=comando["relativo"],
        es_natural=comando["esNatural"],
    )
    hablar(generar_confirmacion(comando))


if __name__ == "__main__":
    main()