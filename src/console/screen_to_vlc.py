# screen_stream_server.py - VERSION ROBUSTA PARA WINDOWS
import cv2
import numpy as np
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time
from PIL import Image
import io
import socket
import traceback

# Intentar importar mss (mas rapido y confiable que pyautogui en Windows)
try:
    import mss
    MSS_AVAILABLE = True
    print("[+] Usando mss para captura (mas rapido)")
except ImportError:
    MSS_AVAILABLE = False
    print("[!] mss no instalado, usando pyautogui (mas lento)")
    print("[!] Instala mss para mejor rendimiento: pip install mss")

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

class ScreenCapture:
    """Clase para capturar pantalla con fallback entre metodos"""
    
    def __init__(self):
        self.mss = None
        if MSS_AVAILABLE:
            try:
                self.mss = mss.mss()
                # Obtener monitor principal
                self.monitor = self.mss.monitors[1]  # 0 = todos, 1 = primario
                print(f"[+] Monitor detectado: {self.monitor['width']}x{self.monitor['height']}")
            except Exception as e:
                print(f"[!] Error iniciando mss: {e}")
                self.mss = None
    
    def capture(self):
        """Captura pantalla intentando multiples metodos"""
        # Metodo 1: mss (mas rapido, C++ backend)
        if self.mss:
            try:
                screenshot = self.mss.grab(self.monitor)
                # Convertir a PIL Image
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                return img
            except Exception as e:
                pass  # Fallback al siguiente metodo
        
        # Metodo 2: pyautogui
        if PYAUTOGUI_AVAILABLE:
            try:
                return pyautogui.screenshot()
            except Exception as e:
                raise e  # No hay mas opciones
        
        raise RuntimeError("No hay metodos de captura disponibles")
    
    def close(self):
        if self.mss:
            self.mss.close()

# Instancia global de captura
screen_capture = ScreenCapture()

class ScreenStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            # Pagina principal
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = """
            <!DOCTYPE html>
            <html>
            <head>
                <title>Screen Stream TV</title>
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    * { margin: 0; padding: 0; box-sizing: border-box; }
                    body { 
                        background: #000; 
                        display: flex; 
                        justify-content: center; 
                        align-items: center; 
                        height: 100vh; 
                        width: 100vw;
                        overflow: hidden; 
                    }
                    img { 
                        width: 100%; 
                        height: 100%; 
                        object-fit: contain; 
                    }
                    #error {
                        position: fixed;
                        top: 50%;
                        left: 50%;
                        transform: translate(-50%, -50%);
                        color: #fff;
                        font-family: Arial, sans-serif;
                        text-align: center;
                        display: none;
                    }
                </style>
            </head>
            <body>
                <img src="/stream" id="stream" onerror="document.getElementById('error').style.display='block'">
                <div id="error">
                    <h2>Error de conexion</h2>
                    <p>Recargando...</p>
                </div>
                <script>
                    // Reconectar automaticamente si falla
                    setInterval(() => {
                        let img = document.getElementById('stream');
                        if (img.naturalWidth === 0) {
                            img.src = '/stream?' + Date.now();
                        }
                    }, 2000);
                </script>
            </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
            
        elif self.path == '/stream':
            # Stream MJPEG
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.end_headers()
            
            consecutive_errors = 0
            max_errors = 10
            
            try:
                while True:
                    try:
                        # Capturar pantalla
                        screenshot = screen_capture.capture()
                        
                        # Convertir a JPEG
                        img_byte_arr = io.BytesIO()
                        screenshot.save(img_byte_arr, format='JPEG', quality=55, optimize=True)
                        img_byte_arr = img_byte_arr.getvalue()
                        
                        # Enviar frame
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(img_byte_arr)}\r\n'.encode('utf-8'))
                        self.wfile.write(b'\r\n')
                        self.wfile.write(img_byte_arr)
                        self.wfile.write(b'\r\n')
                        self.wfile.flush()
                        
                        consecutive_errors = 0  # Resetear contador de errores
                        
                        # Controlar FPS (~20-25 FPS)
                        time.sleep(0.045)
                        
                    except Exception as capture_error:
                        consecutive_errors += 1
                        if consecutive_errors >= max_errors:
                            print(f"[!] Demasiados errores de captura consecutivos, cerrando stream")
                            break
                        
                        # Enviar frame de error (negro) para mantener conexion
                        try:
                            error_img = Image.new('RGB', (640, 480), color='black')
                            draw = ImageDraw.Draw(error_img)
                            draw.text((10, 10), f"Error captura: {str(capture_error)[:50]}", fill=(255, 0, 0))
                            buf = io.BytesIO()
                            error_img.save(buf, 'JPEG', quality=50)
                            data = buf.getvalue()
                            
                            self.wfile.write(b'--frame\r\n')
                            self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                            self.wfile.write(data)
                            self.wfile.write(b'\r\n')
                        except:
                            pass
                        
                        time.sleep(0.5)  # Esperar antes de reintentar
                        
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass  # Cliente desconectado
            except Exception as e:
                print(f"[!] Error en stream: {e}")
                
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        # Solo mostrar conexiones nuevas, no cada frame
        msg = args[0]
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

def run_server(port=8080):
    server = HTTPServer(('0.0.0.0', port), ScreenStreamHandler)
    local_ip = get_local_ip()
    
    print(f"\n{'='*60}")
    print(f"SCREEN STREAM SERVER - ROBUSTO PARA WINDOWS")
    print(f"{'='*60}")
    print(f"URLs disponibles:")
    print(f"   Local:    http://localhost:{port}")
    print(f"   Red:      http://{local_ip}:{port}")
    print(f"{'='*60}")
    print(f"En tu Smart TV:")
    print(f"   1. Abre el navegador del TV")
    print(f"   2. Escribe: http://{local_ip}:{port}")
    print(f"{'='*60}")
    print(f"Presiona Ctrl+C para detener")
    print(f"{'='*60}\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido")
    finally:
        screen_capture.close()

if __name__ == '__main__':
    # Import adicional para dibujar texto en frames de error
    try:
        from PIL import ImageDraw
    except ImportError:
        pass
    
    run_server()