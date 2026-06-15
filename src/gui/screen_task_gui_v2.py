# Python Screen Task v2.0 - Interfaz Grafica Mejorada
# Basado en ScreenTask de Eslam Hamouda y Ahmad Omar
# Version Python GUI por Lenin Ona - 2026
# Mejoras: Fix cuelgue, seleccion monitor, resolucion, milisegundos, audio opcional

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import socket
import time
import io
import webbrowser
import base64
import queue
import sys

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False
    print("[!] Instala mss: pip install mss")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("[!] Instala pyautogui: pip install pyautogui")
    sys.exit(1)

try:
    import sounddevice as sd
    import numpy as np
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False

from PIL import Image
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==================== CONFIGURACION GLOBAL ====================
DEFAULT_PORT = 8080
DEFAULT_QUALITY = 55
DEFAULT_FPS = 25
DEFAULT_MS = 40
# =============================================================

class ScreenCapture:
    def __init__(self, monitor_idx=1, resolution=None):
        self.mss = None
        self.monitor_idx = monitor_idx
        self.resolution = resolution
        if MSS_AVAILABLE:
            try:
                self.mss = mss.MSS()
                self.monitors = self.mss.monitors
                if monitor_idx < len(self.monitors):
                    self.monitor = self.monitors[monitor_idx]
                else:
                    self.monitor = self.monitors[1] if len(self.monitors) > 1 else self.monitors[0]
            except Exception as e:
                print(f"[!] Error iniciando mss: {e}")
                self.mss = None

    def get_monitors_list(self):
        if self.mss:
            return self.mss.monitors
        return []

    def capture(self):
        if self.mss:
            try:
                screenshot = self.mss.grab(self.monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                if self.resolution:
                    img = img.resize(self.resolution, Image.Resampling.LANCZOS)
                return img
            except Exception:
                pass
        if PYAUTOGUI_AVAILABLE:
            img = pyautogui.screenshot()
            if self.resolution:
                img = img.resize(self.resolution, Image.Resampling.LANCZOS)
            return img
        raise RuntimeError("No hay metodos de captura disponibles")

    def close(self):
        if self.mss:
            self.mss.close()

class AudioCapture:
    def __init__(self, sample_rate=44100, channels=2):
        self.sample_rate = sample_rate
        self.channels = channels
        self.running = False
        self.audio_queue = queue.Queue(maxsize=100)
        self.stream = None
        self.thread = None

    def start(self):
        if not AUDIO_AVAILABLE:
            return False
        try:
            self.running = True
            # Intentar capturar audio del sistema (loopback en Windows)
            # Nota: Esto requiere Stereo Mix o similar configurado en Windows
            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=np.int16,
                blocksize=1024,
                callback=self._audio_callback
            )
            self.stream.start()
            return True
        except Exception as e:
            print(f"[!] Error audio: {e}")
            return False

    def _audio_callback(self, indata, frames, time_info, status):
        if self.running:
            try:
                self.audio_queue.put(indata.copy(), block=False)
            except queue.Full:
                pass

    def get_audio_frame(self):
        if not self.audio_queue.empty():
            return self.audio_queue.get()
        return None

    def stop(self):
        self.running = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

class ScreenStreamHandler(BaseHTTPRequestHandler):
    server_instance = None

    def do_GET(self):
        if ScreenStreamHandler.server_instance and ScreenStreamHandler.server_instance.private_mode:
            auth_header = self.headers.get('Authorization', '')
            if not auth_header.startswith('Basic '):
                self.send_response(401)
                self.send_header('WWW-Authenticate', 'Basic realm="ScreenTask"')
                self.end_headers()
                return
            try:
                creds = base64.b64decode(auth_header[6:]).decode('utf-8')
                user, pwd = creds.split(':', 1)
                s = ScreenStreamHandler.server_instance
                if user != s.username or pwd != s.password:
                    self.send_response(401)
                    self.send_header('WWW-Authenticate', 'Basic realm="ScreenTask"')
                    self.end_headers()
                    return
            except Exception:
                self.send_response(401)
                self.send_header('WWW-Authenticate', 'Basic realm="ScreenTask"')
                self.end_headers()
                return

        if self.path == '/':
            if ScreenStreamHandler.server_instance and ScreenStreamHandler.server_instance.vlc_mode:
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                html = ScreenStreamHandler.server_instance.generate_vlc_html()
                self.wfile.write(html.encode('utf-8'))
                return

            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(ScreenStreamHandler.server_instance.html_interface.encode('utf-8'))

        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()

            ScreenStreamHandler.server_instance.add_client(self.client_address)

            try:
                while ScreenStreamHandler.server_instance and ScreenStreamHandler.server_instance.running:
                    try:
                        screenshot = ScreenStreamHandler.server_instance.screen_capture.capture()
                        img_byte_arr = io.BytesIO()
                        quality = ScreenStreamHandler.server_instance.quality
                        screenshot.save(img_byte_arr, format='JPEG', quality=quality, optimize=True)
                        img_byte_arr = img_byte_arr.getvalue()

                        frame_header = b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(img_byte_arr)).encode('utf-8') + b'\r\n\r\n'
                        self.wfile.write(frame_header)
                        self.wfile.write(img_byte_arr)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()

                        ms = ScreenStreamHandler.server_instance.ms_interval
                        time.sleep(ms / 1000.0)

                    except Exception as e:
                        ScreenStreamHandler.server_instance.log(f"Error captura: {e}")
                        time.sleep(0.5)

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as e:
                ScreenStreamHandler.server_instance.log(f"Error stream: {e}")
            finally:
                ScreenStreamHandler.server_instance.remove_client(self.client_address)

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        msg = str(args[0]) if args else ""
        if ScreenStreamHandler.server_instance:
            ScreenStreamHandler.server_instance.log(f"[HTTP] {msg.strip()}")

class ScreenTaskServer:
    def __init__(self, gui):
        self.gui = gui
        self.running = False
        self.server = None
        self.server_thread = None
        self.stop_event = threading.Event()
        self.screen_capture = None
        self.audio_capture = None
        self.clients = set()
        self.clients_lock = threading.Lock()
        self.local_ip = self.get_local_ip()
        self.port = DEFAULT_PORT
        self.quality = DEFAULT_QUALITY
        self.fps = DEFAULT_FPS
        self.ms_interval = DEFAULT_MS
        self.private_mode = False
        self.username = ""
        self.password = ""
        self.vlc_mode = False
        self.monitor_idx = 1
        self.resolution = None
        self.audio_enabled = False
        self.html_interface = ""
        ScreenStreamHandler.server_instance = self

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            ip = "127.0.0.1"
        return ip

    def get_all_ips(self):
        ips = []
        try:
            hostname = socket.gethostname()
            ips_info = socket.getaddrinfo(hostname, None)
            for info in ips_info:
                ip = info[4][0]
                if ip not in ips and not ip.startswith('127.') and ':' not in ip:
                    ips.append(ip)
        except Exception:
            pass
        if not ips:
            ips = [self.local_ip]
        return ips

    def get_monitors_info(self):
        if MSS_AVAILABLE:
            try:
                with mss.MSS() as sct:
                    monitors = []
                    for i, mon in enumerate(sct.monitors):
                        if i == 0:
                            monitors.append(f"Todos los monitores ({mon['width']}x{mon['height']})")
                        else:
                            monitors.append(f"Monitor {i}: {mon['width']}x{mon['height']}")
                    return monitors
            except Exception:
                pass
        return ["Monitor Principal (pyautogui)"]

    def add_client(self, address):
        with self.clients_lock:
            self.clients.add(address)
        self.gui.update_client_count(len(self.clients))

    def remove_client(self, address):
        with self.clients_lock:
            self.clients.discard(address)
        self.gui.update_client_count(len(self.clients))

    def log(self, message):
        self.gui.log(message)

    def start(self, port, quality, fps, ms_interval, private, username, password, 
              vlc_mode=False, monitor_idx=1, resolution=None, audio_enabled=False):
        self.port = port
        self.quality = quality
        self.fps = fps
        self.ms_interval = ms_interval
        self.private_mode = private
        self.username = username
        self.password = password
        self.vlc_mode = vlc_mode
        self.monitor_idx = monitor_idx
        self.resolution = resolution
        self.audio_enabled = audio_enabled

        self.screen_capture = ScreenCapture(monitor_idx, resolution)

        if audio_enabled and AUDIO_AVAILABLE:
            self.audio_capture = AudioCapture()
            if self.audio_capture.start():
                self.log("[+] Captura de audio iniciada")
            else:
                self.log("[!] No se pudo iniciar captura de audio")
                self.audio_capture = None

        if vlc_mode:
            self.html_interface = self.generate_vlc_html()
        else:
            self.html_interface = self.generate_web_html()

        try:
            self.server = HTTPServer(('0.0.0.0', port), ScreenStreamHandler)
            self.running = True
            self.stop_event.clear()
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            return True
        except Exception as e:
            self.log(f"[!] Error iniciando servidor: {e}")
            return False

    def _server_loop(self):
        while not self.stop_event.is_set():
            self.server.timeout = 1.0
            self.server.handle_request()

    def stop(self):
        self.log("Deteniendo servidor...")
        self.running = False
        self.stop_event.set()

        if self.server:
            try:
                # Crear conexion dummy para desbloquear handle_request
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1)
                    s.connect(('127.0.0.1', self.port))
                    s.close()
                except:
                    pass

                self.server.server_close()
                self.server = None
            except Exception as e:
                self.log(f"[!] Error cerrando servidor: {e}")

        if self.screen_capture:
            self.screen_capture.close()
            self.screen_capture = None

        if self.audio_capture:
            self.audio_capture.stop()
            self.audio_capture = None

        with self.clients_lock:
            self.clients.clear()
        self.gui.update_client_count(0)
        self.log("Servidor detenido correctamente")

    def generate_web_html(self):
        return """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Python Screen Task</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1a1a2e; color: #eee; min-height: 100vh; display: flex; flex-direction: column; }
        .header { background: linear-gradient(135deg, #16213e 0%, #0f3460 100%); padding: 15px 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }
        .header h1 { font-size: 1.5rem; color: #e94560; display: flex; align-items: center; gap: 10px; }
        .header h1 .icon { font-size: 1.8rem; }
        .nav-links { display: flex; gap: 15px; flex-wrap: wrap; }
        .nav-links a { color: #a0a0a0; text-decoration: none; padding: 8px 16px; border-radius: 6px; transition: all 0.3s ease; font-size: 0.9rem; }
        .nav-links a:hover { color: #e94560; background: rgba(233, 69, 96, 0.1); }
        .nav-links a.active { color: #e94560; background: rgba(233, 69, 96, 0.15); }
        .main-content { flex: 1; padding: 20px; display: flex; flex-direction: column; align-items: center; max-width: 1400px; margin: 0 auto; width: 100%; }
        .status-bar { display: flex; align-items: center; gap: 20px; margin-bottom: 15px; padding: 10px 20px; background: #16213e; border-radius: 8px; width: 100%; justify-content: center; flex-wrap: wrap; }
        .status-indicator { display: flex; align-items: center; gap: 8px; }
        .status-dot { width: 10px; height: 10px; border-radius: 50%; background: #4ecca3; animation: pulse 2s infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .status-text { font-size: 0.9rem; color: #4ecca3; }
        .viewer-container { width: 100%; background: #0a0a0a; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.4); position: relative; border: 2px solid #16213e; }
        .viewer-container.fullscreen { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 9999; border-radius: 0; border: none; }
        .stream-wrapper { position: relative; width: 100%; padding-bottom: 56.25%; background: #000; }
        .viewer-container.fullscreen .stream-wrapper { padding-bottom: 0; height: 100vh; }
        .stream-image { position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain; background: #000; }
        .loading-overlay { position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; background: rgba(0,0,0,0.8); z-index: 10; transition: opacity 0.3s; }
        .loading-overlay.hidden { opacity: 0; pointer-events: none; }
        .spinner { width: 50px; height: 50px; border: 4px solid #16213e; border-top: 4px solid #e94560; border-radius: 50%; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        .controls { display: flex; justify-content: center; align-items: center; gap: 15px; padding: 15px 20px; background: #16213e; flex-wrap: wrap; }
        .btn { padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9rem; font-weight: 600; display: flex; align-items: center; gap: 8px; transition: all 0.3s ease; }
        .btn:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }
        .btn-success { background: #4ecca3; color: #1a1a2e; }
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; justify-content: center; align-items: center; padding: 20px; }
        .modal-overlay.visible { display: flex; }
        .modal-content { background: #16213e; border-radius: 12px; max-width: 600px; width: 100%; max-height: 80vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.5); border: 1px solid #0f3460; }
        .modal-header { padding: 20px; border-bottom: 1px solid #0f3460; display: flex; justify-content: space-between; align-items: center; }
        .modal-header h2 { color: #e94560; font-size: 1.3rem; }
        .modal-close { background: none; border: none; color: #a0a0a0; font-size: 1.5rem; cursor: pointer; }
        .modal-body { padding: 20px; line-height: 1.6; }
        .modal-body p { margin-bottom: 12px; color: #ccc; }
        .modal-body .highlight { color: #4ecca3; font-weight: 600; }
        .modal-body .project-list { margin: 15px 0; padding-left: 20px; }
        .modal-body .project-list li { margin-bottom: 8px; color: #a0a0a0; }
        .modal-body .project-list a { color: #e94560; text-decoration: none; }
        .footer { background: #16213e; padding: 20px; text-align: center; border-top: 1px solid #0f3460; }
        .footer p { color: #888; font-size: 0.85rem; margin-bottom: 5px; }
        .footer a { color: #e94560; text-decoration: none; }
        @media (max-width: 768px) { .header { flex-direction: column; text-align: center; } .controls { flex-direction: column; } }
    </style>
</head>
<body>
    <header class="header">
        <h1><span class="icon">&#128250;</span>Python Screen Task</h1>
        <nav class="nav-links">
            <a href="./" class="active">Inicio</a>
            <a href="https://github.com/EslaMx7/ScreenTask" target="_blank">Proyecto Windows</a>
            <a href="https://github.com/ahmadomar/ScreenTask" target="_blank">Proyecto Generico</a>
            <a href="#" id="lnkAbout">Acerca de</a>
        </nav>
    </header>
    <main class="main-content">
        <div class="status-bar">
            <div class="status-indicator"><div class="status-dot"></div><span class="status-text">EN VIVO - Transmitiendo pantalla</span></div>
        </div>
        <div class="viewer-container" id="viewerContainer">
            <div class="stream-wrapper"><img id="streamImage" class="stream-image" src="/stream" alt="Transmision en vivo"><div class="loading-overlay" id="loadingOverlay"><div class="spinner"></div></div></div>
            <div class="controls">
                <button id="btnFullscreen" class="btn btn-success"><span>&#9974;</span><span>Pantalla Completa</span></button>
            </div>
        </div>
    </main>
    <div class="modal-overlay" id="modalAbout">
        <div class="modal-content">
            <div class="modal-header"><h2>Acerca de Python Screen Task</h2><button class="modal-close" id="closeAbout">&times;</button></div>
            <div class="modal-body">
                <p><span class="highlight">Comparte tu escritorio con tus amigos dentro de la red interna</span> [No se requiere conexion a Internet]</p>
                <p><strong>Proyectos base:</strong></p>
                <ul class="project-list">
                    <li>Aplicacion Windows desarrollada por: <strong>Eslam Hamouda</strong> | &copy; EslaMxSoft 2014</li>
                    <li>Aplicacion Generica desarrollada por: <strong>Ahmad Omar</strong> | &copy; AhmadOmar 2014</li>
                    <li>Aplicacion Python desarrollada por: <strong>Lenin Ona</strong> | &copy; Python Screen Task 2026</li>
                </ul>
                <p><strong>Enlaces a los proyectos originales:</strong></p>
                <ul class="project-list">
                    <li><a href="https://github.com/EslaMx7/ScreenTask" target="_blank">ScreenTask Windows (EslaMx7)</a></li>
                    <li><a href="https://github.com/ahmadomar/ScreenTask" target="_blank">ScreenTask Generico (ahmadomar)</a></li>
                </ul>
                <p><em>Espero que esto te ayude en tu trabajo!</em></p>
                <p><strong>Envia tu opinion a:</strong></p>
                <p>EslaMx7@Gmail.Com</p>
                <p>ahmad3omar@gmail.com</p>
                <p>orlg.escuela@hotmail.com</p>
            </div>
        </div>
    </div>
    <footer class="footer">
        <p>&copy; Windows Screen Task 2014 | <a href="https://github.com/EslaMx7/ScreenTask" target="_blank">EslaMx7</a></p>
        <p>&copy; Generic Screen Task 2014 | <a href="https://github.com/ahmadomar/ScreenTask" target="_blank">AhmadOmar</a></p>
        <p>&copy; Python Screen Task 2026 | Desarrollado por Lenin Ona</p>
    </footer>
    <script>
        let streamImage = document.getElementById('streamImage');
        let loadingOverlay = document.getElementById('loadingOverlay');
        let viewerContainer = document.getElementById('viewerContainer');
        streamImage.onload = function() { loadingOverlay.classList.add('hidden'); };
        streamImage.onerror = function() { setTimeout(() => { streamImage.src = '/stream?' + Date.now(); }, 2000); };
        document.getElementById('btnFullscreen').onclick = function() {
            if (document.fullscreenElement) { document.exitFullscreen(); } else { viewerContainer.requestFullscreen(); }
        };
        document.getElementById('lnkAbout').onclick = function(e) { e.preventDefault(); document.getElementById('modalAbout').classList.add('visible'); };
        document.getElementById('closeAbout').onclick = function() { document.getElementById('modalAbout').classList.remove('visible'); };
        document.getElementById('modalAbout').onclick = function(e) { if (e.target === this) { this.classList.remove('visible'); } };
    </script>
</body>
</html>"""

    def generate_vlc_html(self):
        return f"""<!DOCTYPE html>
<html><head><title>VLC Stream - Python Screen Task</title>
<style>
body {{ background: #1a1a2e; color: #eee; font-family: 'Segoe UI', Arial; text-align: center; padding: 50px; }}
h1 {{ color: #e94560; }} .url-box {{ background: #16213e; padding: 20px; border-radius: 10px; margin: 30px auto; max-width: 600px; border: 2px solid #0f3460; }}
code {{ background: #0a0a0a; padding: 15px 25px; border-radius: 8px; font-size: 1.1rem; color: #4ecca3; display: inline-block; margin: 10px 0; }}
.steps {{ text-align: left; max-width: 500px; margin: 20px auto; color: #a0a0a0; }}
.steps li {{ margin: 10px 0; }}
.footer {{ margin-top: 40px; font-size: 0.85rem; color: #888; }}
</style></head>
<body>
<h1>&#127909; Transmitiendo a VLC</h1>
<p>El servidor esta en modo VLC. La interfaz web esta deshabilitada.</p>
<div class="url-box">
    <p><strong>URL del stream para VLC:</strong></p>
    <code>http://{self.local_ip}:{self.port}/stream</code>
    <p style="margin-top:15px;color:#888;font-size:0.9rem;">Copia esta URL y pegala en VLC</p>
</div>
<div class="steps">
    <p><strong>Pasos en VLC:</strong></p>
    <ol>
        <li>Abre VLC Media Player</li>
        <li>Ve a <strong>Medio &gt; Abrir flujo de red</strong></li>
        <li>Pega la URL de arriba</li>
        <li>Haz clic en <strong>Reproducir</strong></li>
    </ol>
</div>
<div class="footer">
    <p>Python Screen Task 2026 | Basado en ScreenTask de Eslam Hamouda y Ahmad Omar</p>
</div>
</body></html>"""

class ScreenTaskGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Screen Task v2.0")
        self.root.geometry("750x750")
        self.root.configure(bg="#2d2d2d")
        self.root.resizable(True, True)

        self.server = ScreenTaskServer(self)
        self.server_running = False

        self.build_ui()

    def build_ui(self):
        # ===== HEADER =====
        header_frame = tk.Frame(self.root, bg="#1a1a2e", height=60)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        tk.Label(header_frame, text="SCREEN TASK", font=('Segoe UI', 20, 'bold'), 
                bg="#1a1a2e", fg="#e94560").pack(side=tk.LEFT, padx=20, pady=10)
        tk.Label(header_frame, text="Python Edition 2026", font=('Segoe UI', 10), 
                bg="#1a1a2e", fg="#888888").pack(side=tk.LEFT, pady=10)

        # ===== MAIN CONTENT =====
        main_frame = tk.Frame(self.root, bg="#2d2d2d")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=10)

        # --- Seccion IP y Puerto ---
        ip_frame = tk.LabelFrame(main_frame, text="Configuracion de Red", bg="#2d2d2d", 
                                fg="#e94560", font=('Segoe UI', 11, 'bold'), padx=10, pady=10)
        ip_frame.pack(fill=tk.X, pady=5)

        tk.Label(ip_frame, text="IP Local:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)

        self.ip_combo = ttk.Combobox(ip_frame, values=self.server.get_all_ips(), 
                                     state="readonly", width=25)
        self.ip_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        if self.ip_combo['values']:
            self.ip_combo.current(0)

        tk.Label(ip_frame, text="Puerto:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=0, column=2, sticky=tk.W, padx=(20,0), pady=5)

        self.port_entry = tk.Spinbox(ip_frame, from_=1024, to=65535, width=10, 
                                     font=('Segoe UI', 10), value=DEFAULT_PORT)
        self.port_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)

        tk.Label(ip_frame, text="URL:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=1, column=0, sticky=tk.W, pady=5)

        self.url_entry = tk.Entry(ip_frame, font=('Segoe UI', 10), width=45, 
                                 bg="#1a1a2e", fg="#4ecca3", insertbackground="#ffffff")
        self.url_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        self.update_url()

        self.btn_open_browser = tk.Button(ip_frame, text="Abrir Navegador", 
                                         command=self.open_browser, bg="#0f3460", fg="#ffffff",
                                         font=('Segoe UI', 9), padx=10)
        self.btn_open_browser.grid(row=1, column=3, padx=5, pady=5)

        # --- Seccion Monitor y Resolucion ---
        monitor_frame = tk.LabelFrame(main_frame, text="Pantalla y Resolucion", bg="#2d2d2d", 
                                     fg="#e94560", font=('Segoe UI', 11, 'bold'), padx=10, pady=10)
        monitor_frame.pack(fill=tk.X, pady=5)

        tk.Label(monitor_frame, text="Monitor:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)

        self.monitor_combo = ttk.Combobox(monitor_frame, values=self.server.get_monitors_info(), 
                                          state="readonly", width=35)
        self.monitor_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        if self.monitor_combo['values']:
            self.monitor_combo.current(1 if len(self.monitor_combo['values']) > 1 else 0)

        tk.Label(monitor_frame, text="Resolucion:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=0, column=2, sticky=tk.W, padx=(20,0), pady=5)

        self.resolution_combo = ttk.Combobox(monitor_frame, 
            values=["Original", "1920x1080 (Full HD)", "1280x720 (HD)", "854x480 (SD)", "640x360"], 
            state="readonly", width=20)
        self.resolution_combo.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)
        self.resolution_combo.current(0)

        # --- Seccion Privacidad ---
        priv_frame = tk.LabelFrame(main_frame, text="Privacidad", bg="#2d2d2d", 
                                  fg="#e94560", font=('Segoe UI', 11, 'bold'), padx=10, pady=10)
        priv_frame.pack(fill=tk.X, pady=5)

        self.private_var = tk.BooleanVar(value=False)
        self.chk_private = tk.Checkbutton(priv_frame, text="Tarea Privada (requiere usuario y contrasena)", 
                                         variable=self.private_var, bg="#2d2d2d", fg="#ffffff",
                                         selectcolor="#1a1a2e", activebackground="#2d2d2d",
                                         activeforeground="#ffffff", font=('Segoe UI', 10),
                                         command=self.toggle_private)
        self.chk_private.grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=5)

        tk.Label(priv_frame, text="Usuario:", bg="#2d2d2d", fg="#888888", 
                font=('Segoe UI', 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
        self.user_entry = tk.Entry(priv_frame, font=('Segoe UI', 10), width=15, 
                                  bg="#1a1a2e", fg="#ffffff", insertbackground="#ffffff", state="disabled")
        self.user_entry.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        self.user_entry.insert(0, "screen")

        tk.Label(priv_frame, text="Contrasena:", bg="#2d2d2d", fg="#888888", 
                font=('Segoe UI', 10)).grid(row=1, column=2, sticky=tk.W, padx=(20,0), pady=5)
        self.pass_entry = tk.Entry(priv_frame, font=('Segoe UI', 10), width=15, show="*",
                                  bg="#1a1a2e", fg="#ffffff", insertbackground="#ffffff", state="disabled")
        self.pass_entry.grid(row=1, column=3, sticky=tk.W, padx=5, pady=5)
        self.pass_entry.insert(0, "task")

        # --- Seccion Calidad y Tiempo ---
        quality_frame = tk.LabelFrame(main_frame, text="Calidad y Velocidad", bg="#2d2d2d", 
                                     fg="#e94560", font=('Segoe UI', 11, 'bold'), padx=10, pady=10)
        quality_frame.pack(fill=tk.X, pady=5)

        tk.Label(quality_frame, text="Calidad JPEG:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)
        self.quality_scale = tk.Scale(quality_frame, from_=30, to=95, orient=tk.HORIZONTAL, 
                                     length=150, bg="#2d2d2d", fg="#ffffff", 
                                     highlightthickness=0, troughcolor="#0f3460",
                                     activebackground="#e94560")
        self.quality_scale.set(DEFAULT_QUALITY)
        self.quality_scale.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        tk.Label(quality_frame, text="Milisegundos:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=0, column=2, sticky=tk.W, padx=(20,0), pady=5)
        self.ms_entry = tk.Spinbox(quality_frame, from_=20, to=2000, width=8, 
                                   font=('Segoe UI', 10), value=DEFAULT_MS)
        self.ms_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)

        tk.Label(quality_frame, text="FPS:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=0, column=4, sticky=tk.W, padx=(20,0), pady=5)
        self.fps_spin = tk.Spinbox(quality_frame, from_=5, to=60, width=8, 
                                  font=('Segoe UI', 10), value=DEFAULT_FPS)
        self.fps_spin.grid(row=0, column=5, sticky=tk.W, padx=5, pady=5)

        # --- Audio ---
        self.audio_var = tk.BooleanVar(value=False)
        self.chk_audio = tk.Checkbutton(quality_frame, text="Capturar Audio (experimental)", 
                                       variable=self.audio_var, bg="#2d2d2d", fg="#ffffff",
                                       selectcolor="#1a1a2e", activebackground="#2d2d2d",
                                       activeforeground="#ffffff", font=('Segoe UI', 10))
        self.chk_audio.grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=5)
        if not AUDIO_AVAILABLE:
            self.chk_audio.config(state="disabled")
            tk.Label(quality_frame, text="(Instala sounddevice y numpy para audio)", 
                    bg="#2d2d2d", fg="#888888", font=('Segoe UI', 9)).grid(row=1, column=1, columnspan=5, sticky=tk.W, padx=(200,0), pady=5)

        # --- Botones de Control ---
        btn_frame = tk.Frame(main_frame, bg="#2d2d2d")
        btn_frame.pack(fill=tk.X, pady=10)

        self.btn_start = tk.Button(btn_frame, text="INICIAR SERVIDOR", command=self.start_server,
                                  bg="#4ecca3", fg="#1a1a2e", font=('Segoe UI', 12, 'bold'),
                                  padx=30, pady=10, cursor="hand2")
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(btn_frame, text="DETENER SERVIDOR", command=self.stop_server,
                                 bg="#e94560", fg="#ffffff", font=('Segoe UI', 12, 'bold'),
                                 padx=30, pady=10, cursor="hand2", state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_vlc = tk.Button(btn_frame, text="TRANSMITIR A VLC", command=self.start_vlc_mode,
                                bg="#0f3460", fg="#ffffff", font=('Segoe UI', 12, 'bold'),
                                padx=20, pady=10, cursor="hand2")
        self.btn_vlc.pack(side=tk.RIGHT, padx=5)

        # --- Contador de Clientes ---
        self.client_label = tk.Label(main_frame, text="Clientes conectados: 0", 
                                    bg="#2d2d2d", fg="#4ecca3", font=('Segoe UI', 11, 'bold'))
        self.client_label.pack(pady=5)

        # --- Consola ---
        console_frame = tk.LabelFrame(main_frame, text="Consola de Mensajes", bg="#2d2d2d", 
                                     fg="#e94560", font=('Segoe UI', 11, 'bold'), padx=5, pady=5)
        console_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.console = scrolledtext.ScrolledText(console_frame, wrap=tk.WORD, 
                                                 font=('Consolas', 9), bg="#0a0a0a", 
                                                 fg="#4ecca3", insertbackground="#ffffff",
                                                 state="disabled", height=10)
        self.console.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # --- Footer ---
        footer = tk.Frame(self.root, bg="#1a1a2e", height=30)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        tk.Label(footer, text="Python Screen Task 2026 | Basado en ScreenTask de Eslam Hamouda y Ahmad Omar", 
                bg="#1a1a2e", fg="#888888", font=('Segoe UI', 8)).pack(pady=5)

        # Eventos
        self.ip_combo.bind("<<ComboboxSelected>>", lambda e: self.update_url())
        self.port_entry.bind("<KeyRelease>", lambda e: self.update_url())

    def toggle_private(self):
        state = "normal" if self.private_var.get() else "disabled"
        self.user_entry.config(state=state)
        self.pass_entry.config(state=state)

    def update_url(self):
        ip = self.ip_combo.get() or self.server.local_ip
        port = self.port_entry.get()
        self.url_entry.delete(0, tk.END)
        self.url_entry.insert(0, f"http://{ip}:{port}")

    def open_browser(self):
        url = self.url_entry.get()
        webbrowser.open(url)

    def log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.console.config(state="normal")
        self.console.insert(tk.END, f"[{timestamp}] {message}\n")
        self.console.see(tk.END)
        self.console.config(state="disabled")

    def update_client_count(self, count):
        self.client_label.config(text=f"Clientes conectados: {count}")

    def get_resolution(self):
        res_text = self.resolution_combo.get()
        if res_text == "Original":
            return None
        elif res_text == "1920x1080 (Full HD)":
            return (1920, 1080)
        elif res_text == "1280x720 (HD)":
            return (1280, 720)
        elif res_text == "854x480 (SD)":
            return (854, 480)
        elif res_text == "640x360":
            return (640, 360)
        return None

    def start_server(self, vlc_mode=False):
        if self.server_running:
            return

        try:
            port = int(self.port_entry.get())
            quality = int(self.quality_scale.get())
            fps = int(self.fps_spin.get())
            ms_interval = int(self.ms_entry.get())
            private = self.private_var.get()
            username = self.user_entry.get() if private else ""
            password = self.pass_entry.get() if private else ""
            monitor_idx = self.monitor_combo.current()
            resolution = self.get_resolution()
            audio_enabled = self.audio_var.get() and AUDIO_AVAILABLE

            self.log(f"Iniciando servidor en puerto {port}...")
            self.log(f"Monitor seleccionado: {self.monitor_combo.get()}")
            if resolution:
                self.log(f"Resolucion de salida: {resolution[0]}x{resolution[1]}")

            if self.server.start(port, quality, fps, ms_interval, private, username, password, 
                                vlc_mode, monitor_idx, resolution, audio_enabled):
                self.server_running = True
                self.btn_start.config(state="disabled")
                self.btn_stop.config(state="normal")
                self.btn_vlc.config(state="disabled")

                mode_text = "MODO VLC" if vlc_mode else "modo Web"
                self.log(f"Servidor iniciado correctamente en {mode_text}")
                self.log(f"URL: http://{self.server.local_ip}:{port}")
                self.log(f"Calidad: {quality} | MS: {ms_interval}ms | FPS: {fps}")

                if private:
                    self.log("Modo privado activado - Se requiere autenticacion")

                if audio_enabled:
                    self.log("[+] Captura de audio activada (experimental)")
                    self.log("[!] Nota: El audio requiere Stereo Mix configurado en Windows")

                if vlc_mode:
                    self.log("=" * 50)
                    self.log("MODO VLC ACTIVADO")
                    self.log("La interfaz web esta deshabilitada")
                    self.log(f"Abre VLC y usa: http://{self.server.local_ip}:{port}/stream")
                    self.log("=" * 50)

                    vlc_url = f"http://{self.server.local_ip}:{port}/stream"
                    messagebox.showinfo("Modo VLC", 
                        f"El servidor esta transmitiendo en modo VLC.\n\n"
                        f"URL para VLC:\n{vlc_url}\n\n"
                        f"Pasos:\n"
                        f"1. Abre VLC Media Player\n"
                        f"2. Ve a Medio > Abrir flujo de red\n"
                        f"3. Pega la URL de arriba\n"
                        f"4. Haz clic en Reproducir")
            else:
                self.log("[!] Error al iniciar el servidor")

        except Exception as e:
            self.log(f"[!] Error: {e}")
            messagebox.showerror("Error", f"No se pudo iniciar el servidor:\n{e}")

    def start_vlc_mode(self):
        self.start_server(vlc_mode=True)

    def stop_server(self):
        if not self.server_running:
            return

        self.log("Solicitando detencion del servidor...")
        self.server.stop()
        self.server_running = False

        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.btn_vlc.config(state="normal")

        self.log("Listo - Servidor detenido")

def main():
    root = tk.Tk()
    app = ScreenTaskGUI(root)

    def on_closing():
        if app.server_running:
            app.server.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == '__main__':
    main()
