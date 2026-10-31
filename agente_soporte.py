"""
================================================================================
PRÁCTICA 2: MI AGENTE EN LA NUBE
Despliegue del Agente de Soporte con GitHub Actions
================================================================================
Descripción:
Versión preparada para la nube del agente de soporte.
- Lee credenciales confidenciales desde variables de entorno (.env en local o
  Secrets en GitHub Actions / Docker / Railway).
- Soporta ejecución headless (sin abrir navegador) mediante GOOGLE_TOKEN_JSON.
- Soporta ejecución puntual (--una-vez) con códigos de salida (exit codes) para
  runners de integración continua (CI/CD).
================================================================================
"""

import json
import os
import sys
import time
import schedule
import gspread
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Cargar variables de entorno desde archivo .env local si existe
load_dotenv()

# ==============================================================================
# CONFIGURACIÓN Y CONSTANTES
# ==============================================================================
ARCHIVO_CREDENCIALES = "client_secrets.json"
NOMBRE_HOJA = "Respuestas de Quejas (Base de Datos)"

# Modelo de IA de última generación
MODELO_GEMINI = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

# Lectura de la API Key desde variable de entorno o fallback
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "TU_GEMINI_API_KEY_AQUI")

# Intervalo para el modo continuo local
INTERVALO_MINUTOS = 15

# Scopes requeridos para interactuar con Google Sheets y Google Drive
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Índices de columnas (1-based)
COL_NOMBRE = 2         # Columna B: Tu Nombre
COL_COMENTARIO = 3     # Columna C: Describe tu queja...
COL_CLASIFICACION = 4  # Columna D: Clasificación IA
COL_SENTIMIENTO = 5    # Columna E: Sentimiento IA
COL_EJECUTADO = 6      # Columna F: Agente Ejecutado ('SI')


# ==============================================================================
# FUNCIÓN: CONECTAR CON GOOGLE SHEETS (HÍBRIDO: NUBE O LOCAL)
# ==============================================================================
def conectar_sheets():
    """
    Conecta con Google Sheets con doble estrategia:
    1. Si existe la variable de entorno GOOGLE_TOKEN_JSON (GitHub Actions/Docker/Railway),
       reconstruye las credenciales en memoria, las renueva con refresh() y autoriza gspread
       sin requerir interacción de navegador ni pantalla gráfica.
    2. Si no existe, realiza el flujo OAuth 2.0 interactivo tradicional usando client_secrets.json.
    """
    token_json_str = os.getenv("GOOGLE_TOKEN_JSON")

    try:
        if token_json_str:
            print("[*] Autenticando mediante GOOGLE_TOKEN_JSON (Modo Nube/Headless)...")
            token_info = json.loads(token_json_str)
            creds = Credentials.from_authorized_user_info(token_info, scopes=SCOPES)
            
            # Renovar token si es necesario
            if creds.expired and creds.refresh_token:
                print("[*] Renovando access token expirado con Google OAuth...")
                creds.refresh(Request())
                
            gc = gspread.authorize(creds)
            hoja = gc.open(NOMBRE_HOJA)
            return hoja.sheet1
        else:
            print("[*] Autenticando mediante client_secrets.json local...")
            gc = gspread.oauth(credentials_filename=ARCHIVO_CREDENCIALES)
            hoja = gc.open(NOMBRE_HOJA)
            return hoja.sheet1
    except Exception as e:
        print(f"[ERROR] Error al conectar con Google Sheets: {e}")
        return None


# ==============================================================================
# FUNCIÓN: ANALIZAR CON GEMINI AI
# ==============================================================================
def analizar_con_gemini(comentario: str) -> dict:
    """
    Envía la queja del cliente a Gemini 3.8 Flash con salida estructurada en JSON.
    """
    prompt_usuario = (
        f"Analiza la siguiente queja, sugerencia o comentario de un cliente:\n\n"
        f"\"{comentario}\"\n\n"
        f"Devuelve un objeto JSON con exactamente dos claves:\n"
        f"- \"clasificacion\": Debe ser exactamente una de estas tres opciones: \"Ventas\", \"Soporte Técnico\" o \"Logística\".\n"
        f"- \"sentimiento\": Debe ser exactamente una de estas tres opciones: \"Positivo\", \"Negativo\" o \"Neutro\"."
    )

    config = types.GenerateContentConfig(
        system_instruction=(
            "Eres un analista de soporte al cliente experto. Tu única tarea es clasificar "
            "comentarios de clientes y detectar su sentimiento. Debes responder ÚNICAMENTE "
            "con un objeto JSON válido con las claves 'clasificacion' y 'sentimiento', "
            "sin explicaciones adicionales, sin saludos y sin texto introductorio."
        ),
        response_mime_type="application/json",
        temperature=0.1
    )

    respuesta = cliente_gemini.models.generate_content(
        model=MODELO_GEMINI,
        contents=prompt_usuario,
        config=config
    )

    texto_respuesta = respuesta.text.strip()
    if texto_respuesta.startswith("```json"):
        texto_respuesta = texto_respuesta[7:]
    elif texto_respuesta.startswith("```"):
        texto_respuesta = texto_respuesta[3:]
    if texto_respuesta.endswith("```"):
        texto_respuesta = texto_respuesta[:-3]
    texto_respuesta = texto_respuesta.strip()

    return json.loads(texto_respuesta)


# ==============================================================================
# FUNCIÓN: AGENTE PRINCIPAL
# ==============================================================================
def ejecutar_agente() -> bool:
    """
    Ejecuta un ciclo de procesamiento de la hoja.
    Retorna True si el ciclo concluyó exitosamente o False si hubo un error crítico de conexión.
    """
    print("\n" + "=" * 55)
    print("[AGENTE] Iniciando ciclo de procesamiento...")
    print("=" * 55)

    hoja = conectar_sheets()
    if hoja is None:
        print("[!] No fue posible establecer conexión con Google Sheets.")
        return False

    try:
        filas = hoja.get_all_values()
    except Exception as e:
        print(f"[ERROR] Error al consultar datos de la hoja: {e}")
        return False

    if len(filas) <= 1:
        print("[i] La hoja no contiene registros de clientes actualmente.")
        return True

    filas_datos = filas[1:]
    nuevas_procesadas = 0
    ya_procesadas = 0

    for indice_fila, fila in enumerate(filas_datos, start=2):
        estado_f = fila[COL_EJECUTADO - 1].strip().upper() if len(fila) >= COL_EJECUTADO else ""

        if estado_f == "SI":
            ya_procesadas += 1
            continue

        nombre = fila[COL_NOMBRE - 1].strip() if len(fila) >= COL_NOMBRE and fila[COL_NOMBRE - 1].strip() else "Anónimo"
        comentario = fila[COL_COMENTARIO - 1].strip() if len(fila) >= COL_COMENTARIO else ""

        if not comentario:
            print(f"[!] Fila {indice_fila}: Comentario en blanco, omitiendo.")
            continue

        print(f"\n[+] Procesando queja de: {nombre} (Fila {indice_fila})")
        print(f"    Comentario: \"{comentario}\"")

        try:
            resultado = analizar_con_gemini(comentario)
            clasificacion = resultado.get("clasificacion", "Desconocido")
            sentimiento = resultado.get("sentimiento", "Neutro")

            print(f"    -> Clasificación: {clasificacion}")
            print(f"    -> Sentimiento:   {sentimiento}")

            hoja.update_cell(indice_fila, COL_CLASIFICACION, clasificacion)
            hoja.update_cell(indice_fila, COL_SENTIMIENTO, sentimiento)
            hoja.update_cell(indice_fila, COL_EJECUTADO, "SI")
            print(f"    [OK] Resultado escrito en la fila {indice_fila}.")
            nuevas_procesadas += 1

        except Exception as e:
            print(f"    [ERROR] Fila {indice_fila} falló durante el análisis: {e}")
            print("    [!] La fila permanecerá pendiente para reintento en el siguiente ciclo.")

    print("\n" + "-" * 55)
    print(f"Resumen del ciclo: {nuevas_procesadas} nuevas procesadas | {ya_procesadas} ya procesadas.")
    print("-" * 55)
    return True


# ==============================================================================
# PUNTO DE ENTRADA
# ==============================================================================
if __name__ == "__main__":
    print("\n" + "=" * 65)
    print("      AGENTE DE SOPORTE CLOUD & RUNNER DE CI/CD               ")
    print("=" * 65)

    # 1. Validación de API Key de Gemini
    if not GEMINI_API_KEY or GEMINI_API_KEY == "TU_GEMINI_API_KEY_AQUI" or "Ejemplo" in GEMINI_API_KEY:
        print("\n[ERROR CRÍTICO] Falta configurar la variable GEMINI_API_KEY.")
        print("Configúrala en tu archivo .env o como Secret en GitHub Actions/Docker/Railway.")
        sys.exit(1)

    # 2. Validación de credenciales de Google
    # Solo se exige client_secrets.json si NO viene el token por variable de entorno
    if not os.getenv("GOOGLE_TOKEN_JSON") and not os.path.exists(ARCHIVO_CREDENCIALES):
        print(f"\n[ERROR CRÍTICO] No se encontró '{ARCHIVO_CREDENCIALES}' ni la variable GOOGLE_TOKEN_JSON.")
        print("En local, coloca tu archivo client_secrets.json.")
        print("En la nube, define el Secret / Variable de entorno GOOGLE_TOKEN_JSON.")
        sys.exit(1)

    # 3. Inicializar cliente de Gemini
    cliente_gemini = genai.Client(api_key=GEMINI_API_KEY)

    # 4. Modo de ejecución única (--una-vez) para GitHub Actions o tareas cron
    if "--una-vez" in sys.argv:
        print("[*] Modo de ejecución única (--una-vez) detectado.")
        exito = ejecutar_agente()
        # Retornar código de salida semántico para el runner (0: éxito, 1: fallo)
        sys.exit(0 if exito else 1)

    # 5. Modo continuo (bucle infinito local o en contenedor 24/7)
    print("[*] Modo continuo activado. Ejecutando primera revisión inmediata...")
    ejecutar_agente()

    print(f"\n[*] Programado para ejecutarse automáticamente cada {INTERVALO_MINUTOS} minutos.")
    print("[*] Presiona Ctrl + C para detener el script.\n")
    schedule.every(INTERVALO_MINUTOS).minutes.do(ejecutar_agente)

    while True:
        schedule.run_pending()
        time.sleep(30)

