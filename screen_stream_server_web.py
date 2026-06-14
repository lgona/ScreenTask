# Python Screen Task - Servidor de Streaming de Pantalla
# Basado en ScreenTask de Eslam Hamouda y Ahmad Omar
# Version Python por Lenin Ona - 2026

import io
from http.server import BaseHTTPRequestHandler, HTTPServer
import socket
import time
from PIL import Image

try:
    import mss
    MSS_AVAILABLE = True
    print("[+] Usando mss para captura (mas rapido y confiable)")
except ImportError:
    MSS_AVAILABLE = False
    print("[!] mss no instalado, usando pyautogui")
    print("[!] Instala mss para mejor rendimiento: pip install mss")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("[!] ERROR: Instala pyautogui: pip install pyautogui")
    exit(1)

# ==================== CONFIGURACION ====================
PORT = 8080
QUALITY = 55
FPS_TARGET = 25
CAPTURE_REGION = None
# =======================================================

class ScreenCapture:
    def __init__(self):
        self.mss = None
        if MSS_AVAILABLE:
            try:
                self.mss = mss.MSS()
                self.monitor = self.mss.monitors[1]
                print(f"[+] Monitor detectado: {self.monitor['width']}x{self.monitor['height']}")
            except Exception as e:
                print(f"[!] Error iniciando mss: {e}")
                self.mss = None

    def capture(self):
        if self.mss:
            try:
                screenshot = self.mss.grab(self.monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return img
            except Exception:
                pass

        if PYAUTOGUI_AVAILABLE:
            try:
                if CAPTURE_REGION:
                    return pyautogui.screenshot(region=CAPTURE_REGION)
                return pyautogui.screenshot()
            except Exception as e:
                raise e

        raise RuntimeError("No hay metodos de captura disponibles")

    def close(self):
        if self.mss:
            self.mss.close()

screen_capture = ScreenCapture()

HTML_INTERFACE = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="description" content="Python Screen Task - Comparte tu escritorio en la red local">
    <meta name="author" content="Eslam Hamouda, Ahmad Omar, Lenin Ona">
    <title>Python Screen Task</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: #1a1a2e;
            color: #eee;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .header {
            background: linear-gradient(135deg, #16213e 0%, #0f3460 100%);
            padding: 15px 30px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.3);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
        }
        .header h1 {
            font-size: 1.5rem;
            color: #e94560;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .header h1 .icon { font-size: 1.8rem; }
        .nav-links {
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
        }
        .nav-links a {
            color: #a0a0a0;
            text-decoration: none;
            padding: 8px 16px;
            border-radius: 6px;
            transition: all 0.3s ease;
            font-size: 0.9rem;
        }
        .nav-links a:hover {
            color: #e94560;
            background: rgba(233, 69, 96, 0.1);
        }
        .nav-links a.active {
            color: #e94560;
            background: rgba(233, 69, 96, 0.15);
        }
        .main-content {
            flex: 1;
            padding: 20px;
            display: flex;
            flex-direction: column;
            align-items: center;
            max-width: 1400px;
            margin: 0 auto;
            width: 100%;
        }
        .status-bar {
            display: flex;
            align-items: center;
            gap: 20px;
            margin-bottom: 15px;
            padding: 10px 20px;
            background: #16213e;
            border-radius: 8px;
            width: 100%;
            justify-content: center;
            flex-wrap: wrap;
        }
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #4ecca3;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        .status-text {
            font-size: 0.9rem;
            color: #4ecca3;
        }
        .fps-counter {
            font-family: 'Courier New', monospace;
            color: #a0a0a0;
            font-size: 0.85rem;
        }
        .viewer-container {
            width: 100%;
            background: #0a0a0a;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0,0,0,0.4);
            position: relative;
            border: 2px solid #16213e;
        }
        .viewer-container.fullscreen {
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            z-index: 9999;
            border-radius: 0;
            border: none;
        }
        .stream-wrapper {
            position: relative;
            width: 100%;
            padding-bottom: 56.25%;
            background: #000;
        }
        .viewer-container.fullscreen .stream-wrapper {
            padding-bottom: 0;
            height: 100vh;
        }
        .stream-image {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: contain;
            background: #000;
        }
        .viewer-container.fullscreen .stream-image {
            object-fit: contain;
        }
        .loading-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: rgba(0,0,0,0.8);
            z-index: 10;
            transition: opacity 0.3s;
        }
        .loading-overlay.hidden {
            opacity: 0;
            pointer-events: none;
        }
        .spinner {
            width: 50px;
            height: 50px;
            border: 4px solid #16213e;
            border-top: 4px solid #e94560;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .loading-text {
            margin-top: 15px;
            color: #a0a0a0;
            font-size: 0.9rem;
        }
        .error-overlay {
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            display: none;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: rgba(0,0,0,0.9);
            z-index: 20;
        }
        .error-overlay.visible { display: flex; }
        .error-icon {
            font-size: 3rem;
            color: #e94560;
            margin-bottom: 10px;
        }
        .error-text {
            color: #a0a0a0;
            font-size: 1rem;
        }
        .controls {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 15px;
            padding: 15px 20px;
            background: #16213e;
            flex-wrap: wrap;
        }
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.3s ease;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
        }
        .btn:active { transform: translateY(0); }
        .btn-primary {
            background: #e94560;
            color: white;
        }
        .btn-primary:hover { background: #ff6b6b; }
        .btn-secondary {
            background: #0f3460;
            color: #eee;
        }
        .btn-secondary:hover { background: #1a4a7a; }
        .btn-success {
            background: #4ecca3;
            color: #1a1a2e;
        }
        .btn-success:hover { background: #6ee7c7; }
        .interval-control {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .interval-control label {
            font-size: 0.85rem;
            color: #a0a0a0;
        }
        .interval-control input {
            width: 80px;
            padding: 8px 12px;
            border: 1px solid #0f3460;
            border-radius: 6px;
            background: #1a1a2e;
            color: #eee;
            text-align: center;
            font-size: 0.9rem;
        }
        .interval-control input:focus {
            outline: none;
            border-color: #e94560;
        }
        .modal-overlay {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.7);
            z-index: 10000;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }
        .modal-overlay.visible { display: flex; }
        .modal-content {
            background: #16213e;
            border-radius: 12px;
            max-width: 600px;
            width: 100%;
            max-height: 80vh;
            overflow-y: auto;
            box-shadow: 0 20px 60px rgba(0,0,0,0.5);
            border: 1px solid #0f3460;
        }
        .modal-header {
            padding: 20px;
            border-bottom: 1px solid #0f3460;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .modal-header h2 {
            color: #e94560;
            font-size: 1.3rem;
        }
        .modal-close {
            background: none;
            border: none;
            color: #a0a0a0;
            font-size: 1.5rem;
            cursor: pointer;
            padding: 0;
            width: 30px;
            height: 30px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 50%;
            transition: all 0.3s;
        }
        .modal-close:hover {
            background: rgba(233, 69, 96, 0.2);
            color: #e94560;
        }
        .modal-body {
            padding: 20px;
            line-height: 1.6;
        }
        .modal-body p {
            margin-bottom: 12px;
            color: #ccc;
        }
        .modal-body .highlight {
            color: #4ecca3;
            font-weight: 600;
        }
        .modal-body .project-list {
            margin: 15px 0;
            padding-left: 20px;
        }
        .modal-body .project-list li {
            margin-bottom: 8px;
            color: #a0a0a0;
        }
        .modal-body .project-list a {
            color: #e94560;
            text-decoration: none;
        }
        .modal-body .project-list a:hover { text-decoration: underline; }
        .modal-footer {
            padding: 15px 20px;
            border-top: 1px solid #0f3460;
            text-align: center;
            font-style: italic;
            color: #888;
        }
        .footer {
            background: #16213e;
            padding: 20px;
            text-align: center;
            border-top: 1px solid #0f3460;
        }
        .footer p {
            color: #888;
            font-size: 0.85rem;
            margin-bottom: 5px;
        }
        .footer a {
            color: #e94560;
            text-decoration: none;
        }
        .footer a:hover { text-decoration: underline; }
        .fullscreen-hint {
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(233, 69, 96, 0.9);
            color: white;
            padding: 10px 20px;
            border-radius: 8px;
            font-size: 0.85rem;
            z-index: 10001;
            opacity: 0;
            transition: opacity 0.3s;
            pointer-events: none;
        }
        .fullscreen-hint.visible { opacity: 1; }
        @media (max-width: 768px) {
            .header { flex-direction: column; text-align: center; }
            .header h1 { font-size: 1.2rem; }
            .nav-links { justify-content: center; }
            .controls { flex-direction: column; }
            .interval-control { width: 100%; justify-content: center; }
        }
    </style>
</head>
<body>
    <header class="header">
        <h1>
            <span class="icon">&#128250;</span>
            Python Screen Task
        </h1>
        <nav class="nav-links">
            <a href="./" class="active">Inicio</a>
            <a href="https://github.com/EslaMx7/ScreenTask" target="_blank">Proyecto Windows</a>
            <a href="https://github.com/ahmadomar/ScreenTask" target="_blank">Proyecto Generico</a>
            <a href="#" id="lnkAbout">Acerca de</a>
        </nav>
    </header>

    <main class="main-content">
        <div class="status-bar">
            <div class="status-indicator">
                <div class="status-dot"></div>
                <span class="status-text">EN VIVO - Transmitiendo pantalla</span>
            </div>
            <div class="fps-counter" id="fpsCounter">FPS: --</div>
        </div>

        <div class="viewer-container" id="viewerContainer">
            <div class="stream-wrapper" id="streamWrapper">
                <img id="streamImage" class="stream-image" src="/stream" alt="Transmision en vivo">
                <div class="loading-overlay" id="loadingOverlay">
                    <div class="spinner"></div>
                    <div class="loading-text">Conectando al stream...</div>
                </div>
                <div class="error-overlay" id="errorOverlay">
                    <div class="error-icon">&#9888;</div>
                    <div class="error-text" id="errorText">Error de conexion</div>
                </div>
            </div>

            <div class="controls">
                <button id="btnStartStop" class="btn btn-primary" data-state="playing">
                    <span id="btnIcon">&#9208;</span>
                    <span id="btnText">Pausar</span>
                </button>
                <div class="interval-control">
                    <label for="txtInterval">Intervalo (ms):</label>
                    <input type="number" id="txtInterval" value="40" min="20" max="2000" step="10">
                    <button id="btnSetInterval" class="btn btn-secondary">Aplicar</button>
                </div>
                <button id="btnFullscreen" class="btn btn-success">
                    <span>&#9974;</span>
                    <span>Pantalla Completa</span>
                </button>
            </div>
        </div>
    </main>

    <div class="fullscreen-hint" id="fullscreenHint">
        Presiona ESC o F11 para salir de pantalla completa
    </div>

    <div class="modal-overlay" id="modalAbout">
        <div class="modal-content">
            <div class="modal-header">
                <h2>Acerca de Python Screen Task</h2>
                <button class="modal-close" id="closeAbout">&times;</button>
            </div>
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
                    <li><a href="https://github.com/lgona/ScreenTask" target="_blank">ScreenTask Python (lgona)</a></li>
                </ul>
                <p><em>Espero que esto te ayude en tu trabajo!</em></p>
                <p><strong>Envia tu opinion a:</strong></p>
                <p>EslaMx7@Gmail.Com</p>
                <p>ahmad3omar@gmail.com</p>
                <p>orlg.escuela@hotmail.com</p>
            </div>
            <div class="modal-footer">
                Python Screen Task 2026 - Software de Codigo Abierto
            </div>
        </div>
    </div>

    <footer class="footer">
        <p>&copy; Windows Screen Task 2014 | <a href="https://github.com/EslaMx7/ScreenTask" target="_blank">EslaMx7</a></p>
        <p>&copy; Generic Screen Task 2014 | <a href="https://github.com/ahmadomar/ScreenTask" target="_blank">AhmadOmar</a></p>
        <p>&copy; Python Screen Task 2026 | <a href="https://github.com/lgona/ScreenTask" target="_blank">lgona</a>Desarrollado por Lenin Ona</p>
    </footer>

    <script>
        let refreshInterval = 40;
        let isPlaying = true;
        let timer = null;
        let frameCount = 0;
        let lastTime = Date.now();
        let streamImage = document.getElementById('streamImage');
        let loadingOverlay = document.getElementById('loadingOverlay');
        let errorOverlay = document.getElementById('errorOverlay');
        let errorText = document.getElementById('errorText');
        let fpsCounter = document.getElementById('fpsCounter');
        let viewerContainer = document.getElementById('viewerContainer');
        let fullscreenHint = document.getElementById('fullscreenHint');

        function startStream() {
            if (timer) clearInterval(timer);
            streamImage.src = '/stream';
            loadingOverlay.classList.remove('hidden');
            errorOverlay.classList.remove('visible');
            streamImage.onload = function() {
                loadingOverlay.classList.add('hidden');
            };
            streamImage.onerror = function() {
                loadingOverlay.classList.add('hidden');
                errorText.textContent = 'Error al cargar el stream. Reintentando...';
                errorOverlay.classList.add('visible');
            };
        }

        function stopStream() {
            if (timer) {
                clearInterval(timer);
                timer = null;
            }
            streamImage.src = '';
        }

        function updateFPS() {
            frameCount++;
            let now = Date.now();
            let elapsed = now - lastTime;
            if (elapsed >= 1000) {
                let fps = Math.round((frameCount * 1000) / elapsed);
                fpsCounter.textContent = 'FPS: ' + fps;
                frameCount = 0;
                lastTime = now;
            }
        }

        setInterval(updateFPS, 1000);

        let btnStartStop = document.getElementById('btnStartStop');
        let btnIcon = document.getElementById('btnIcon');
        let btnText = document.getElementById('btnText');

        btnStartStop.onclick = function() {
            if (isPlaying) {
                isPlaying = false;
                stopStream();
                btnStartStop.classList.remove('btn-primary');
                btnStartStop.classList.add('btn-success');
                btnIcon.innerHTML = '&#9654;';
                btnText.textContent = 'Reproducir';
            } else {
                isPlaying = true;
                startStream();
                btnStartStop.classList.remove('btn-success');
                btnStartStop.classList.add('btn-primary');
                btnIcon.innerHTML = '&#9208;';
                btnText.textContent = 'Pausar';
            }
        };

        let txtInterval = document.getElementById('txtInterval');
        let btnSetInterval = document.getElementById('btnSetInterval');

        btnSetInterval.onclick = function() {
            let newInterval = parseInt(txtInterval.value);
            if (newInterval >= 20 && newInterval <= 2000) {
                refreshInterval = newInterval;
                if (isPlaying) {
                    startStream();
                }
                btnSetInterval.textContent = 'Aplicado!';
                setTimeout(() => {
                    btnSetInterval.textContent = 'Aplicar';
                }, 1000);
            }
        };

        let btnFullscreen = document.getElementById('btnFullscreen');

        function enterFullscreen() {
            viewerContainer.classList.add('fullscreen');
            if (viewerContainer.requestFullscreen) {
                viewerContainer.requestFullscreen();
            } else if (viewerContainer.webkitRequestFullscreen) {
                viewerContainer.webkitRequestFullscreen();
            } else if (viewerContainer.mozRequestFullScreen) {
                viewerContainer.mozRequestFullScreen();
            } else if (viewerContainer.msRequestFullscreen) {
                viewerContainer.msRequestFullscreen();
            }
            fullscreenHint.classList.add('visible');
            setTimeout(() => {
                fullscreenHint.classList.remove('visible');
            }, 3000);
            btnFullscreen.innerHTML = '<span>&#8634;</span><span>Salir Pantalla Completa</span>';
        }

        function exitFullscreen() {
            viewerContainer.classList.remove('fullscreen');
            if (document.exitFullscreen) {
                document.exitFullscreen();
            } else if (document.webkitExitFullscreen) {
                document.webkitExitFullscreen();
            } else if (document.mozCancelFullScreen) {
                document.mozCancelFullScreen();
            } else if (document.msExitFullscreen) {
                document.msExitFullscreen();
            }
            btnFullscreen.innerHTML = '<span>&#9974;</span><span>Pantalla Completa</span>';
        }

        btnFullscreen.onclick = function() {
            if (document.fullscreenElement || 
                document.webkitFullscreenElement || 
                document.mozFullScreenElement || 
                document.msFullscreenElement) {
                exitFullscreen();
            } else {
                enterFullscreen();
            }
        };

        document.addEventListener('fullscreenchange', onFullscreenChange);
        document.addEventListener('webkitfullscreenchange', onFullscreenChange);
        document.addEventListener('mozfullscreenchange', onFullscreenChange);
        document.addEventListener('MSFullscreenChange', onFullscreenChange);

        function onFullscreenChange() {
            if (!document.fullscreenElement && 
                !document.webkitFullscreenElement && 
                !document.mozFullScreenElement && 
                !document.msFullscreenElement) {
                viewerContainer.classList.remove('fullscreen');
                btnFullscreen.innerHTML = '<span>&#9974;</span><span>Pantalla Completa</span>';
            }
        }

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' || e.key === 'F11') {
                if (viewerContainer.classList.contains('fullscreen')) {
                    exitFullscreen();
                }
            }
        });

        let lnkAbout = document.getElementById('lnkAbout');
        let modalAbout = document.getElementById('modalAbout');
        let closeAbout = document.getElementById('closeAbout');

        lnkAbout.onclick = function(e) {
            e.preventDefault();
            modalAbout.classList.add('visible');
        };

        closeAbout.onclick = function() {
            modalAbout.classList.remove('visible');
        };

        modalAbout.onclick = function(e) {
            if (e.target === modalAbout) {
                modalAbout.classList.remove('visible');
            }
        };

        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape' && modalAbout.classList.contains('visible')) {
                modalAbout.classList.remove('visible');
            }
        });

        window.onload = function() {
            startStream();
        };

        streamImage.onerror = function() {
            if (isPlaying) {
                setTimeout(() => {
                    streamImage.src = '/stream?' + Date.now();
                }, 2000);
            }
        };
    </script>
</body>
</html>"""

class ScreenStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_INTERFACE.encode('utf-8'))

        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()

            consecutive_errors = 0
            max_errors = 10
            frame_delay = 1.0 / FPS_TARGET

            try:
                while True:
                    try:
                        start_time = time.time()
                        screenshot = screen_capture.capture()
                        img_byte_arr = io.BytesIO()
                        screenshot.save(img_byte_arr, format='JPEG', quality=QUALITY, optimize=True)
                        img_byte_arr = img_byte_arr.getvalue()

                        frame_header = b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' + str(len(img_byte_arr)).encode('utf-8') + b'\r\n\r\n'
                        self.wfile.write(frame_header)
                        self.wfile.write(img_byte_arr)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()

                        consecutive_errors = 0
                        elapsed = time.time() - start_time
                        sleep_time = frame_delay - elapsed
                        if sleep_time > 0:
                            time.sleep(sleep_time)

                    except Exception as capture_error:
                        consecutive_errors += 1
                        if consecutive_errors >= max_errors:
                            print("[!] Demasiados errores consecutivos, cerrando stream")
                            break
                        try:
                            error_img = Image.new('RGB', (640, 480), color='black')
                            buf = io.BytesIO()
                            error_img.save(buf, 'JPEG', quality=50)
                            data = buf.getvalue()
                            self.wfile.write(b'--frame\r\nContent-Type: image/jpeg\r\n\r\n')
                            self.wfile.write(data)
                            self.wfile.write(b'\r\n')
                        except:
                            pass
                        time.sleep(0.5)

            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as e:
                print(f"[!] Error en stream: {e}")

        else:
            self.send_error(404)

    def log_message(self, format, *args):
        msg = str(args[0]) if args else ""
        if "GET /stream" not in msg and "GET /favicon.ico" not in msg:
            print(f"[+] {msg.strip()}")

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        IP = s.getsockname()[0]
        s.close()
    except Exception:
        IP = "127.0.0.1"
    return IP

def run_server(port=PORT):
    server = HTTPServer(('0.0.0.0', port), ScreenStreamHandler)
    local_ip = get_local_ip()

    print(f"\n{'='*60}")
    print(f"  PYTHON SCREEN TASK - SERVIDOR DE STREAMING")
    print(f"{'='*60}")
    print(f"  Basado en ScreenTask de Eslam Hamouda y Ahmad Omar")
    print(f"  Version Python por Lenin Ona - 2026")
    print(f"{'='*60}")
    print(f"  URLs disponibles:")
    print(f"     Local:    http://localhost:{port}")
    print(f"     Red:      http://{local_ip}:{port}")
    print(f"{'='*60}")
    print(f"  En tu Smart TV:")
    print(f"     1. Abre el navegador del TV")
    print(f"     2. Escribe: http://{local_ip}:{port}")
    print(f"     3. Listo! Veras tu pantalla en tiempo real")
    print(f"{'='*60}")
    print(f"  Configuracion:")
    print(f"     Calidad JPEG: {QUALITY}")
    print(f"     FPS Target: {FPS_TARGET}")
    print(f"     Puerto: {port}")
    print(f"{'='*60}")
    print(f"  Presiona Ctrl+C para detener el servidor")
    print(f"{'='*60}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Servidor detenido por el usuario")
    finally:
        screen_capture.close()
        print("[+] Recursos liberados correctamente")

if __name__ == '__main__':
    run_server()