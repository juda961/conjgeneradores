import ctypes
import io
import os
import re
import sqlite3
import subprocess
import tempfile
import time
import wave
from datetime import datetime

from ddgs import DDGS
from fastapi import FastAPI, File, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from piper import PiperVoice
from pydantic import BaseModel
import pyautogui
import pygetwindow as gw
import requests

# Intento de importar win32com para resolver accesos directos de Windows (.lnk)
try:
    import win32com.client
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

# Intento de importar pycaw, comtypes y pythoncom para control de volumen preciso
try:
    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    import pythoncom
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

# Teclas multimedia nativas de Windows
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP = 0xAF
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_PLAY_PAUSE = 0xB3

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/app")
def servir_chat():
    return FileResponse("static/index.html")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "llama3.1:8b"
DB_PATH = "jarvis.db"
MENSAJES_DE_CONTEXTO = 10

WORKSPACE_DIR = os.path.abspath("./workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# --- INDEXACIÓN DINÁMICA DE APLICACIONES ---
APPS_DINAMICAS = {}

def indexar_programas_instalados():
    """Escanea el Menú Inicio de Windows para indexar accesos directos (.lnk)."""
    global APPS_DINAMICAS
    APPS_DINAMICAS.clear()

    APPS_DINAMICAS.update({
        "calculadora": {"cmd": "calc.exe", "exe": "CalculatorApp.exe"},
        "calc": {"cmd": "calc.exe", "exe": "CalculatorApp.exe"},
        "bloc de notas": {"cmd": "notepad.exe", "exe": "notepad.exe"},
        "block de notas": {"cmd": "notepad.exe", "exe": "notepad.exe"},
        "notepad": {"cmd": "notepad.exe", "exe": "notepad.exe"},
        "cmd": {"cmd": "cmd.exe", "exe": "cmd.exe"},
        "símbolo del sistema": {"cmd": "cmd.exe", "exe": "cmd.exe"},
        "explorador de archivos": {"cmd": "explorer.exe", "exe": "explorer.exe"}
    })

    if not WIN32_AVAILABLE:
        print("Aviso: 'pywin32' no está instalado. Usando solo aplicaciones base.")
        return

    rutas_start_menu = [
        os.path.join(os.environ.get("PROGRAMDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs")
    ]

    try:
        shell = win32com.client.Dispatch("WScript.Shell")
        for ruta_base in rutas_start_menu:
            if not os.path.exists(ruta_base):
                continue
            for root, _, files in os.walk(ruta_base):
                for file in files:
                    if file.endswith(".lnk"):
                        nombre_clean = file.replace(".lnk", "").lower().strip()
                        ruta_lnk = os.path.join(root, file)
                        try:
                            shortcut = shell.CreateShortCut(ruta_lnk)
                            target = shortcut.Targetpath
                            if target and target.endswith(".exe") and "uninstall" not in nombre_clean:
                                APPS_DINAMICAS[nombre_clean] = {
                                    "cmd": target,
                                    "exe": os.path.basename(target)
                                }
                        except Exception:
                            pass
        print(f"Indexación completada: {len(APPS_DINAMICAS)} programas detectados.")
    except Exception as e:
        print(f"Error indexando accesos directos: {e}")

indexar_programas_instalados()

# --- MODELOS DE VOZ Y AUDIO ---
whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

piper_voice = PiperVoice.load(
    "es_MX-ald-medium.onnx",
    espeak_data_dir="venv/Lib/site-packages/piper/espeak-ng-data"
)

# --- BASE DE DATOS SEGURA ---
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversacion (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rol TEXT NOT NULL,
                texto TEXT NOT NULL,
                fecha TEXT NOT NULL
            )
        """)

def guardar_mensaje(rol, texto):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO conversacion (rol, texto, fecha) VALUES (?, ?, ?)",
            (rol, texto, datetime.now().isoformat())
        )

def obtener_mensajes_historial():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT rol, texto FROM conversacion ORDER BY id DESC LIMIT ?",
            (MENSAJES_DE_CONTEXTO,)
        )
        filas = cursor.fetchall()

    filas.reverse()
    mensajes = []
    for rol, texto in filas:
        role = "user" if rol == "usuario" else "assistant"
        mensajes.append({"role": role, "content": texto})
    return mensajes

init_db()

# --- FUNCIONES Y HERRAMIENTAS DE SISTEMA Y VENTANAS ---
def enfocar_ventana(nombre_app):
    """Busca si la ventana ya existe para enfocarla con un delay adecuado."""
    ventanas = gw.getWindowsWithTitle('')
    for win in ventanas:
        if win.title and nombre_app.lower() in win.title.lower():
            try:
                if win.isMinimized:
                    win.restore()
                win.activate()
                time.sleep(0.5)
                return True
            except Exception as e:
                print(f"Error al enfocar ventana: {e}")
    return False

def hora_actual():
    return datetime.now().strftime("Hoy es %A %d de %B de %Y, y son las %H:%M")

def calculadora(expresion):
    if not re.match(r'^[\d\s\.\+\-\*\/\(\)]+$', expresion):
        return "Error: expresión no válida"
    try:
        resultado = eval(expresion, {"__builtins__": {}}, {})
        return str(resultado)
    except Exception as e:
        return f"Error al calcular: {e}"

def buscar_internet(consulta):
    try:
        resultados = DDGS().text(consulta, max_results=4)
        if not resultados:
            return "No se encontraron resultados."
        texto = ""
        for r in resultados:
            texto += f"- {r['title']}: {r['body']}\n"
        return texto
    except Exception as e:
        return f"Error al buscar: {e}"

def buscar_app(nombre_app):
    query = nombre_app.lower().strip()
    if query in APPS_DINAMICAS:
        return query, APPS_DINAMICAS[query]
    for clave, data in APPS_DINAMICAS.items():
        if query in clave or clave in query:
            return clave, data
    return None, None

def abrir_aplicacion(nombre_app):
    nombre_encontrado, app_data = buscar_app(nombre_app)

    target_search = nombre_encontrado if nombre_encontrado else nombre_app
    if enfocar_ventana(target_search):
        return f"Ventana de '{target_search}' enfocada."

    if app_data:
        try:
            subprocess.Popen(app_data["cmd"])
            return f"Aplicación '{nombre_encontrado}' ejecutada correctamente."
        except Exception as e:
            return f"Error al ejecutar {nombre_encontrado}: {e}"
    return f"No encontré la aplicación '{nombre_app}' instalada."

def cerrar_aplicacion(nombre_app):
    nombre_encontrado, app_data = buscar_app(nombre_app)
    exe_target = app_data["exe"] if app_data else f"{nombre_app.strip()}.exe"

    try:
        resultado = subprocess.run(["taskkill", "/F", "/IM", exe_target], capture_output=True, text=True)
        if resultado.returncode == 0:
            return f"Aplicación '{exe_target}' cerrada correctamente."
        return f"No se pudo cerrar '{exe_target}'. Es posible que no esté en ejecución."
    except Exception as e:
        return f"Error al intentar cerrar {exe_target}: {e}"

# --- CONTROL DE VOLUMEN Y MULTIMEDIA INTELIGENTE ---
def presionar_tecla_multimedia(vk_code):
    scan_code = ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)
    ctypes.windll.user32.keybd_event(vk_code, scan_code, KEYEVENTF_EXTENDEDKEY, 0)
    ctypes.windll.user32.keybd_event(vk_code, scan_code, KEYEVENTF_EXTENDEDKEY | KEYEVENTF_KEYUP, 0)

def obtener_volumen_actual():
    if not PYCAW_AVAILABLE:
        return None
    try:
        pythoncom.CoInitialize()
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
        return int(round(volume.GetMasterVolumeLevelScalar() * 100))
    except Exception as e:
        print(f"Error obteniendo volumen: {e}")
        return None
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

def fijar_volumen_porcentaje(porcentaje):
    if PYCAW_AVAILABLE:
        try:
            pythoncom.CoInitialize()
            devices = AudioUtilities.GetSpeakers()
            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            volume = ctypes.cast(interface, ctypes.POINTER(IAudioEndpointVolume))
            nivel = max(0.0, min(1.0, porcentaje / 100.0))
            volume.SetMasterVolumeLevelScalar(nivel, None)
            return True
        except Exception as e:
            print(f"[Aviso Volume Pycaw]: {e}. Usando respaldo por teclado...")
        finally:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    try:
        for _ in range(50):
            presionar_tecla_multimedia(VK_VOLUME_DOWN)
        pasos_subida = int(round(porcentaje / 2.0))
        for _ in range(pasos_subida):
            presionar_tecla_multimedia(VK_VOLUME_UP)
        return True
    except Exception as e:
        print(f"[Error Teclado Volume]: {e}")
        return False

def controlar_volumen(accion, nivel=None):
    accion = accion.lower().strip()

    if nivel is not None:
        try:
            nivel = int(nivel)
        except (ValueError, TypeError):
            nivel = None

    if accion == "fijar" and nivel is not None:
        if fijar_volumen_porcentaje(nivel):
            return f"Volumen fijado al {nivel}%."
        return "No se pudo cambiar el volumen exacto."
    elif accion == "subir":
        vol_actual = obtener_volumen_actual()
        if vol_actual is not None and nivel is not None:
            nuevo_vol = min(100, vol_actual + nivel)
            fijar_volumen_porcentaje(nuevo_vol)
            return f"Volumen subido del {vol_actual}% al {nuevo_vol}%."
        pasos = max(1, (nivel // 2)) if nivel else 5
        for _ in range(pasos):
            presionar_tecla_multimedia(VK_VOLUME_UP)
        return "Volumen subido."
    elif accion == "bajar":
        vol_actual = obtener_volumen_actual()
        if vol_actual is not None and nivel is not None:
            nuevo_vol = max(0, vol_actual - nivel)
            fijar_volumen_porcentaje(nuevo_vol)
            return f"Volumen bajado del {vol_actual}% al {nuevo_vol}%."
        pasos = max(1, (nivel // 2)) if nivel else 5
        for _ in range(pasos):
            presionar_tecla_multimedia(VK_VOLUME_DOWN)
        return "Volumen bajado."
    elif accion in ["silenciar", "mutear", "desmutear"]:
        presionar_tecla_multimedia(VK_VOLUME_MUTE)
        return "Silencio alternado (Mute/Unmute)."
    return "Acción de volumen no reconocida."

def detectar_app_sonando():
    """Revisa qué proceso tiene una sesión de audio activa ahora mismo."""
    if not PYCAW_AVAILABLE:
        return None
    try:
        pythoncom.CoInitialize()
        sesiones = AudioUtilities.GetAllSessions()
        for sesion in sesiones:
            if sesion.Process and sesion.State == 1:  # 1 = AudioSessionStateActive
                return sesion.Process.name().lower()
        return None
    except Exception as e:
        print(f"Error detectando app sonando: {e}")
        return None
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

def app_esta_sonando(nombre_proceso_parcial):
    """Verifica si una app específica tiene sesión de audio ACTIVA (sonando de verdad)."""
    if not PYCAW_AVAILABLE:
        return None
    try:
        pythoncom.CoInitialize()
        sesiones = AudioUtilities.GetAllSessions()
        for sesion in sesiones:
            if sesion.Process and nombre_proceso_parcial in sesion.Process.name().lower():
                return sesion.State == 1
        return None
    except Exception as e:
        print(f"Error verificando estado de audio: {e}")
        return None
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass

def controlar_multimedia(accion, destino="general"):
    accion = accion.lower().strip()
    destino = destino.lower().strip() if destino else "general"

    if destino == "general":
        app_activa = detectar_app_sonando()
        if app_activa:
            if "spotify" in app_activa:
                destino = "spotify"
            elif any(k in app_activa for k in ["brave", "chrome", "msedge", "firefox"]):
                destino = "youtube"
            print(f"🎧 App detectada sonando: {app_activa} → destino = {destino}")

    proceso_buscar = "spotify" if "spotify" in destino else (
        "brave" if any(k in destino for k in ["youtube", "brave", "navegador", "video"]) else None
    )

    # Con el enum, 'accion' siempre llega como "pausar", "reproducir", "siguiente" o "anterior"
    if proceso_buscar and accion in ["pausar", "reproducir"]:
        esta_sonando = app_esta_sonando(proceso_buscar)
        if esta_sonando is True and accion == "reproducir":
            return f"{destino} ya está reproduciendo."
        if esta_sonando is False and accion == "pausar":
            return f"{destino} ya está en pausa."

    if any(k in destino for k in ["youtube", "brave", "navegador", "video"]):
        if enfocar_ventana("youtube") or enfocar_ventana("brave"):
            pyautogui.press('k')
            return f"Reproducción alternada en {destino}."
        return "No encontré la ventana de YouTube o Brave activa."

    elif "spotify" in destino:
        if enfocar_ventana("spotify"):
            pyautogui.press('space')
            return "Reproducción alternada en Spotify."
        else:
            presionar_tecla_multimedia(VK_MEDIA_PLAY_PAUSE)
            return "Reproducción alternada en Spotify (global)."

    else:
        if accion in ["reproducir", "pausar"]:
            presionar_tecla_multimedia(VK_MEDIA_PLAY_PAUSE)
            return "Reproducción alternada del sistema (Play/Pausa)."
        elif accion == "siguiente":
            presionar_tecla_multimedia(VK_MEDIA_NEXT_TRACK)
            return "Siguiente pista."
        elif accion == "anterior":
            presionar_tecla_multimedia(VK_MEDIA_PREV_TRACK)
            return "Pista anterior."
    return "Acción multimedia no reconocida."

# --- MANEJO DE NOTAS Y ARCHIVOS ---
def guardar_nota(nombre_archivo, contenido):
    ruta_segura = os.path.abspath(os.path.join(WORKSPACE_DIR, nombre_archivo))
    if os.path.commonpath([WORKSPACE_DIR, ruta_segura]) != WORKSPACE_DIR:
        return "Error de seguridad: Intento de acceder fuera de workspace."
    try:
        with open(ruta_segura, "w", encoding="utf-8") as f:
            f.write(contenido)
        return f"Archivo '{nombre_archivo}' guardado con éxito."
    except Exception as e:
        return f"Error al guardar: {e}"

def leer_nota(nombre_archivo):
    ruta_segura = os.path.abspath(os.path.join(WORKSPACE_DIR, nombre_archivo))
    if os.path.commonpath([WORKSPACE_DIR, ruta_segura]) != WORKSPACE_DIR:
        return "Error de seguridad: Intento de acceder fuera de workspace."
    if not os.path.exists(ruta_segura):
        return f"El archivo '{nombre_archivo}' no existe."
    try:
        with open(ruta_segura, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error al leer: {e}"

def listar_notas():
    try:
        archivos = os.listdir(WORKSPACE_DIR)
        if not archivos:
            return "El directorio de trabajo está vacío."
        return "Archivos guardados:\n" + "\n".join(f"- {a}" for a in archivos)
    except Exception as e:
        return f"Error al listar archivos: {e}"

# --- ESQUEMA DE HERRAMIENTAS PARA OLLAMA ---
HERRAMIENTAS = [
    {
        "type": "function",
        "function": {
            "name": "hora_actual",
            "description": "Devuelve la fecha y hora actual",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculadora",
            "description": "Calcula expresiones matemáticas simples",
            "parameters": {
                "type": "object",
                "properties": {
                    "expresion": {"type": "string", "description": "Ej: '23 * 4 + 1'"}
                },
                "required": ["expresion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_internet",
            "description": "Busca información actual en internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "consulta": {"type": "string", "description": "Términos de búsqueda"}
                },
                "required": ["consulta"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_aplicacion",
            "description": "Abre o enfoca un programa o aplicación en la laptop",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_app": {"type": "string", "description": "Nombre de la aplicación (ej: brave, chrome, bloc de notas, vs code, spotify)"}
                },
                "required": ["nombre_app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cerrar_aplicacion",
            "description": "Cierra o finaliza la ejecución de un programa en la laptop",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_app": {"type": "string", "description": "Nombre del programa a cerrar (ej: brave, calculadora, notepad)"}
                },
                "required": ["nombre_app"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "controlar_volumen",
            "description": "Controla el volumen de Windows.\nREGLAS DE SELECCIÓN:\n1. Si la frase indica un volumen OBJETIVO O FINAL (ej: 'baja AL 20%', 'bájale AL 30%', 'sube AL 80%', 'ponlo EN 50%', 'fija en 30%'), la acción DEBE ser 'fijar'.\n2. Si es un cambio RELATIVO (ej: 'baja EN 20%', 'bájale 10 puntos', 'baja un poco'), la acción es 'bajar'.\n3. Si es un incremento RELATIVO (ej: 'sube EN 20%', 'sube 10 puntos'), la acción es 'subir'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "description": "'fijar' (para metas 'AL X%'), 'subir' (relativo 'EN X%'), 'bajar' (relativo 'EN X%') o 'silenciar'"
                    },
                    "nivel": {
                        "type": "integer",
                        "description": "Porcentaje de 0 a 100"
                    }
                },
                "required": ["accion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "controlar_multimedia",
            "description": "Controla la reproducción de música/videos especificando claramente el servicio de destino ('youtube', 'brave', 'spotify' o 'general').",
            "parameters": {
                "type": "object",
                "properties": {
                    "accion": {
                        "type": "string",
                        "enum": ["reproducir", "pausar", "siguiente", "anterior"],
                        "description": "Acción EXACTA a realizar. Usa 'pausar' si el usuario dice pausa/detener/para. Usa 'reproducir' si dice play/continúa/dale."
                    },
                    "destino": {
                        "type": "string",
                        "description": "Servicio o app mencionada por el usuario (ej: 'youtube', 'brave', 'spotify', 'general')"
                    }
                },
                "required": ["accion"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "guardar_nota",
            "description": "Guarda un archivo de texto en la carpeta de trabajo",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_archivo": {"type": "string", "description": "Ej: notas.txt"},
                    "contenido": {"type": "string", "description": "Texto del archivo"}
                },
                "required": ["nombre_archivo", "contenido"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "leer_nota",
            "description": "Leer el contenido de un archivo guardado",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombre_archivo": {"type": "string", "description": "Nombre del archivo a leer"}
                },
                "required": ["nombre_archivo"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "listar_notas",
            "description": "Lista los archivos guardados en el workspace",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    }
]

def ejecutar_herramienta(nombre, argumentos):
    if nombre == "hora_actual":
        return hora_actual()
    elif nombre == "calculadora":
        return calculadora(argumentos.get("expresion", ""))
    elif nombre == "buscar_internet":
        return buscar_internet(argumentos.get("consulta", ""))
    elif nombre == "abrir_aplicacion":
        return abrir_aplicacion(argumentos.get("nombre_app", ""))
    elif nombre == "cerrar_aplicacion":
        return cerrar_aplicacion(argumentos.get("nombre_app", ""))
    elif nombre == "controlar_volumen":
        return controlar_volumen(argumentos.get("accion", ""), argumentos.get("nivel"))
    elif nombre == "controlar_multimedia":
        return controlar_multimedia(argumentos.get("accion", ""), argumentos.get("destino", "general"))
    elif nombre == "guardar_nota":
        return guardar_nota(argumentos.get("nombre_archivo", ""), argumentos.get("contenido", ""))
    elif nombre == "leer_nota":
        return leer_nota(argumentos.get("nombre_archivo", ""))
    elif nombre == "listar_notas":
        return listar_notas()
    return "Herramienta no encontrada"

class Mensaje(BaseModel):
    texto: str

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "Eres Jarvis, un asistente virtual con acceso TOTAL para controlar el volumen, la música/multimedia y aplicaciones del sistema Windows.\n"
        "JAMÁS digas 'no puedo realizar cambios' o 'no tengo acceso al sistema'. Tienes herramientas para hacerlo.\n\n"
        "REGLAS OBLIGATORIAS:\n"
        "- Si el usuario menciona reproducir, pausar o continuar algo en 'YouTube', 'Brave' o 'Spotify', DEBES pasar explícitamente el nombre de esa app en el argumento `destino` de la herramienta `controlar_multimedia` (ej. destino='youtube', destino='spotify').\n"
        "- Si el usuario pide pausar/reproducir música de forma genérica sin especificar aplicación, usa `controlar_multimedia` con destino='general'.\n"
        "- Si el usuario dice 'baja AL X%', 'sube AL X%' o 'ponlo AL X%', usa `controlar_volumen` con accion='fijar' y nivel=X."
    )
}

# --- ENDPOINTS ---
@app.post("/chat")
def chat(mensaje: Mensaje):
    historial = obtener_mensajes_historial()
    messages = [SYSTEM_PROMPT] + historial + [{"role": "user", "content": mensaje.texto}]

    payload = {
        "model": MODEL,
        "messages": messages,
        "tools": HERRAMIENTAS,
        "stream": False,
        "options": {"num_ctx": 2048}
    }

    respuesta = requests.post(OLLAMA_URL, json=payload).json()
    msg = respuesta["message"]

    if msg.get("tool_calls"):
        messages.append(msg)
        for tool_call in msg["tool_calls"]:
            nombre = tool_call["function"]["name"]
            argumentos = tool_call["function"]["arguments"]
            print(f"🔧 Herramienta: {nombre} | Argumentos: {argumentos}")
            resultado = ejecutar_herramienta(nombre, argumentos)
            messages.append({"role": "tool", "content": str(resultado)})

        payload["messages"] = messages
        respuesta2 = requests.post(OLLAMA_URL, json=payload).json()
        texto_respuesta = respuesta2["message"]["content"].strip()
    else:
        texto_respuesta = msg["content"].strip()

    guardar_mensaje("usuario", mensaje.texto)
    guardar_mensaje("jarvis", texto_respuesta)

    return {"respuesta": texto_respuesta}

@app.post("/transcribir")
def transcribir(audio: UploadFile = File(...)):
    with tempfile.NamedTemporaryFile(delete=False, suffix=".webm") as tmp:
        tmp.write(audio.file.read())
        tmp_path = tmp.name

    try:
        segments, _ = whisper_model.transcribe(tmp_path, language="es")
        texto = " ".join(segment.text for segment in segments).strip()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    return {"texto": texto}

@app.post("/hablar")
def hablar(mensaje: Mensaje):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        piper_voice.synthesize_wav(mensaje.texto, wav_file)
    return Response(content=buffer.getvalue(), media_type="audio/wav")

@app.get("/historial")
def historial():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT rol, texto, fecha FROM conversacion ORDER BY id ASC")
        filas = cursor.fetchall()
    return [{"rol": r, "texto": t, "fecha": f} for r, t, f in filas]

@app.get("/")
def home():
    return {"status": "Jarvis está vivo 🟢"}