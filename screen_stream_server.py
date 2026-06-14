# screen_stream_server.py - VERSION CORREGIDA PARA WINDOWS
import cv2
import numpy as np
import pyautogui
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import time
from PIL import Image
import io
import socket

class ScreenStreamHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            # Pagina principal optimizada para TV
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # HTML sin emojis ni acentos para evitar errores de bytes
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
                    #status {
                        position: fixed;
                        top: 10px;
                        left: 10px;
                        color: #0f0;
                        font-family: monospace;
                        background: rgba(0,0,0,0.7);
                        padding: 5px 10px;
                        border-radius: 5px;
                        font-size: 14px;
                    }
                </style>
            </head>
            <body>
                <div id="status">Conectado - Cargando stream...</div>
                <img src="/stream" alt="Screen Stream" onload="document.getElementById('status').style.display='none'">
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
            
            frame_count = 0
            start_time = time.time()
            
            try:
                while True:
                    # Capturar pantalla completa
                    screenshot = pyautogui.screenshot()
                    
                    # Convertir a JPEG
                    img_byte_arr = io.BytesIO()
                    screenshot.save(img_byte_arr, format='JPEG', quality=60, optimize=True)
                    img_byte_arr = img_byte_arr.getvalue()
                    
                    # Enviar frame
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n')
                    self.wfile.write(f'Content-Length: {len(img_byte_arr)}\r\n'.encode('utf-8'))
                    self.wfile.write(b'\r\n')
                    self.wfile.write(img_byte_arr)
                    self.wfile.write(b'\r\n')
                    
                    self.wfile.flush()
                    
                    frame_count += 1
                    
                    # Calcular FPS real
                    elapsed = time.time() - start_time
                    if elapsed >= 1.0:
                        fps_real = frame_count / elapsed
                        frame_count = 0
                        start_time = time.time()
                    
                    # Controlar velocidad (~25 FPS)
                    time.sleep(0.04)
                    
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as e:
                print(f"Error en stream: {e}")
                
        else:
            self.send_error(404)
    
    def log_message(self, format, *args):
        if "GET /stream" not in args[0]:
            print(f"[+] {args[0]}")

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
    print(f"SCREEN STREAM SERVER - 100% PYTHON")
    print(f"{'='*60}")
    print(f"NO REQUIERE FFMPEG - Funciona inmediatamente")
    print(f"{'='*60}")
    print(f"URLs disponibles:")
    print(f"   Local:    http://localhost:{port}")
    print(f"   Red:      http://{local_ip}:{port}")
    print(f"{'='*60}")
    print(f"En tu Smart TV:")
    print(f"   1. Abre el navegador del TV")
    print(f"   2. Escribe: http://{local_ip}:{port}")
    print(f"   3. Listo! Veras tu pantalla en tiempo real")
    print(f"{'='*60}")
    print(f"Presiona Ctrl+C para detener el servidor")
    print(f"{'='*60}\n")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido correctamente")

if __name__ == '__main__':
    run_server()