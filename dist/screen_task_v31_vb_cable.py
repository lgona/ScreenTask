# Python Screen Task v3.1 - Audio VB-CABLE Integration
# Basado en ScreenTask de Eslam Hamouda y Ahmad Omar
# Version Python GUI por Lenin Ona - 2026
# Mejoras: Audio por endpoint separado /audio usando VB-CABLE, sin ffmpeg necesario

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
import os
import struct
import wave
import tempfile
from collections import deque
import subprocess
import platform
import signal

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
    print("[!] ERROR: Instala pyautogui: pip install pyautogui")
    sys.exit(1)

try:
    import pyaudiowpatch as pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    try:
        import pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False
        print("[!] Instala PyAudioWPatch: pip install PyAudioWPatch")

from PIL import Image
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==================== CONFIGURACION GLOBAL ====================
DEFAULT_PORT = 8080
DEFAULT_QUALITY = 55
DEFAULT_FPS = 25
DEFAULT_MS = 40
MAX_CLIENTS = 5
FAVICON_PATH = "favicon.png"
AUDIO_PORT = 5000  # Puerto interno para captura de audio VB-CABLE
# =============================================================

class ScreenCapture:
    def __init__(self, monitor_idx=1, resolution=None):
        self.mss = None
        self.monitor_idx = monitor_idx
        self.resolution = resolution
        if MSS_AVAILABLE:
            try:
                self.mss = mss.mss()
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


class VBCableAudioCapture:
    """Captura audio usando VB-CABLE Virtual Audio Device o cualquier dispositivo de entrada.
    Sirve el audio por HTTP en un puerto dedicado."""

    def __init__(self, device_index=None, sample_rate=44100, channels=2, chunk_size=1024):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.running = False
        self.audio_queue = queue.Queue(maxsize=200)
        self.stream = None
        self.pa = None
        self.lock = threading.Lock()
        self.server = None
        self.server_thread = None
        self.audio_port = AUDIO_PORT
        self.actual_rate = 44100
        self.actual_channels = 2
        self.clients_count = 0
        self.clients_lock = threading.Lock()

    def get_input_devices(self):
        """Obtiene lista de dispositivos de entrada disponibles"""
        devices = []
        if not PYAUDIO_AVAILABLE:
            return devices
        try:
            pa_temp = pyaudio.PyAudio()
            for i in range(pa_temp.get_device_count()):
                try:
                    info = pa_temp.get_device_info_by_index(i)
                    if info.get('maxInputChannels', 0) > 0:
                        devices.append({
                            'index': i,
                            'name': info.get('name', 'Unknown'),
                            'channels': int(info.get('maxInputChannels', 2)),
                            'rate': int(info.get('defaultSampleRate', 44100))
                        })
                except:
                    continue
            pa_temp.terminate()
        except Exception as e:
            print(f"[!] Error listando dispositivos: {e}")
        return devices

    def find_vb_cable(self):
        """Busca especificamente el dispositivo VB-CABLE"""
        if not PYAUDIO_AVAILABLE:
            return None
        try:
            pa_temp = pyaudio.PyAudio()
            for i in range(pa_temp.get_device_count()):
                try:
                    info = pa_temp.get_device_info_by_index(i)
                    name = info.get('name', '').lower()
                    if 'vb-audio' in name or 'cable' in name or 'virtual' in name:
                        if info.get('maxInputChannels', 0) > 0:
                            pa_temp.terminate()
                            return i
                except:
                    continue
            pa_temp.terminate()
        except:
            pass
        return None

    def start(self, device_index=None):
        if not PYAUDIO_AVAILABLE:
            return False

        self.audio_queue = queue.Queue(maxsize=200)

        try:
            self.pa = pyaudio.PyAudio()

            if device_index is not None:
                self.device_index = device_index
            elif self.device_index is None:
                # Intentar encontrar VB-CABLE automaticamente
                vb_idx = self.find_vb_cable()
                if vb_idx is not None:
                    self.device_index = vb_idx
                    print(f"[AUDIO] VB-CABLE detectado automaticamente en indice {vb_idx}")
                else:
                    # Usar dispositivo de entrada por defecto
                    try:
                        default_info = self.pa.get_default_input_device_info()
                        self.device_index = default_info['index']
                    except:
                        return False

            device_info = self.pa.get_device_info_by_index(self.device_index)
            self.actual_rate = int(device_info.get('defaultSampleRate', 44100))
            max_channels = int(device_info.get('maxInputChannels', 2))
            self.actual_channels = min(max_channels, self.channels)

            print(f"[AUDIO] Dispositivo: {device_info.get('name')}")
            print(f"[AUDIO] Canales: {self.actual_channels}, Rate: {self.actual_rate}")

            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=self.actual_channels,
                rate=self.actual_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=self.chunk_size,
                stream_callback=self._audio_callback
            )

            self.running = True
            self.stream.start_stream()

            # Iniciar servidor HTTP de audio en puerto dedicado
            self._start_audio_server()

            return True

        except Exception as e:
            print(f"[!] Error iniciando audio: {e}")
            if self.pa:
                try:
                    self.pa.terminate()
                except:
                    pass
                self.pa = None
            return False

    def _audio_callback(self, in_data, frame_count, time_info, status):
        if self.running and in_data:
            # Limpiar cola si esta muy llena
            if self.audio_queue.qsize() > 180:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
            try:
                self.audio_queue.put_nowait(in_data)
            except queue.Full:
                pass
        return (None, pyaudio.paContinue)

    def _start_audio_server(self):
        """Inicia el servidor HTTP dedicado para el stream de audio"""
        try:
            self.server = HTTPServer(('0.0.0.0', self.audio_port), self._create_audio_handler())
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()
            print(f"[AUDIO] Servidor de audio iniciado en puerto {self.audio_port}")
        except Exception as e:
            print(f"[!] Error iniciando servidor de audio: {e}")

    def _server_loop(self):
        while self.running and self.server:
            self.server.timeout = 1.0
            try:
                self.server.handle_request()
            except:
                pass

    def _create_audio_handler(self):
        """Factory para crear el handler con referencia a esta instancia"""
        audio_capture = self

        class AudioStreamHandler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, format, *args):
                pass  # Silenciar logs HTTP

            def do_GET(self):
                if self.path == '/' or self.path == '/audio' or self.path.startswith('/audio'):
                    self.send_audio_stream()
                elif self.path == '/status':
                    self.send_status()
                else:
                    self.send_error(404)

            def send_status(self):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                status = f'{{"status":"streaming","port":{audio_capture.audio_port},'
                status += f'"format":"audio/wav","channels":{audio_capture.actual_channels},'
                status += f'"rate":{audio_capture.actual_rate}}}'
                self.wfile.write(status.encode())

            def send_audio_stream(self):
                client_ip = self.client_address[0]
                print(f"[AUDIO] Cliente conectado: {client_ip}")

                with audio_capture.clients_lock:
                    audio_capture.clients_count += 1

                self.send_response(200)
                self.send_header('Content-Type', 'audio/wav')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

                # Escribir cabecera WAV
                wav_header = self._create_wav_header()
                self.wfile.write(wav_header)

                chunks_sent = 0
                last_activity = time.time()

                try:
                    while audio_capture.running:
                        try:
                            audio_data = audio_capture.audio_queue.get(timeout=2.0)
                            self.wfile.write(audio_data)
                            chunks_sent += 1
                            last_activity = time.time()
                        except queue.Empty:
                            # Enviar silencio si no hay datos por 2 segundos
                            if time.time() - last_activity > 3:
                                silence = b'\x00' * (audio_capture.chunk_size * audio_capture.actual_channels * 2)
                                self.wfile.write(silence)
                                last_activity = time.time()
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                    pass
                except Exception as e:
                    print(f"[AUDIO] Error en stream: {e}")
                finally:
                    with audio_capture.clients_lock:
                        audio_capture.clients_count -= 1
                    print(f"[AUDIO] Cliente desconectado: {client_ip}")

            def _create_wav_header(self):
                data_size = 0x7FFFFFFF
                byte_rate = audio_capture.actual_rate * audio_capture.actual_channels * 2
                block_align = audio_capture.actual_channels * 2

                header = bytearray()
                header.extend(b'RIFF')
                header.extend(struct.pack('<I', 36 + data_size))
                header.extend(b'WAVE')
                header.extend(b'fmt ')
                header.extend(struct.pack('<I', 16))
                header.extend(struct.pack('<H', 1))  # PCM
                header.extend(struct.pack('<H', audio_capture.actual_channels))
                header.extend(struct.pack('<I', audio_capture.actual_rate))
                header.extend(struct.pack('<I', byte_rate))
                header.extend(struct.pack('<H', block_align))
                header.extend(struct.pack('<H', 16))  # 16-bit
                header.extend(b'data')
                header.extend(struct.pack('<I', data_size))
                return bytes(header)

        return AudioStreamHandler

    def get_audio_url(self, host_ip):
        """Retorna la URL completa del stream de audio"""
        return f"http://{host_ip}:{self.audio_port}/audio"

    def get_clients_count(self):
        with self.clients_lock:
            return self.clients_count

    def stop(self):
        self.running = False
        if self.server:
            try:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1)
                    s.connect(('127.0.0.1', self.audio_port))
                    s.close()
                except:
                    pass
                self.server.server_close()
                self.server = None
            except:
                pass

        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except:
                pass
            self.stream = None
        if self.pa:
            try:
                self.pa.terminate()
            except:
                pass
            self.pa = None

        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except:
                break

        print("[AUDIO] Captura de audio detenida")


class ScreenStreamHandler(BaseHTTPRequestHandler):
    server_instance = None

    def do_GET(self):
        if self.path == '/favicon.ico':
            self.send_favicon()
            return

        s = ScreenStreamHandler.server_instance
        if s and s.private_mode:
            auth_header = self.headers.get('Authorization', '')
            if not auth_header.startswith('Basic '):
                self.send_response(401)
                self.send_header('WWW-Authenticate', 'Basic realm="ScreenTask"')
                self.end_headers()
                return
            try:
                creds = base64.b64decode(auth_header[6:]).decode('utf-8')
                user, pwd = creds.split(':', 1)
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
            if s and s.vlc_mode:
                self.send_response(200)
                self.send_header('Content-type', 'text/html; charset=utf-8')
                self.end_headers()
                html = s.generate_vlc_html()
                self.wfile.write(html.encode('utf-8'))
                return

            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(s.html_interface.encode('utf-8'))

        elif self.path == '/stream':
            self.send_stream()

        elif self.path == '/audio':
            self.redirect_to_audio_server()

        else:
            self.send_error(404)

    def send_favicon(self):
        try:
            if os.path.exists(FAVICON_PATH):
                with open(FAVICON_PATH, 'rb') as f:
                    data = f.read()
                self.send_response(200)
                self.send_header('Content-type', 'image/png')
                self.send_header('Content-Length', len(data))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(404)
        except Exception:
            self.send_error(404)

    def redirect_to_audio_server(self):
        s = ScreenStreamHandler.server_instance
        if not s or not s.audio_capture or not s.audio_capture.running:
            self.send_error(503, "Servidor de audio no disponible")
            return

        self.send_response(200)
        self.send_header('Content-Type', 'audio/wav')
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()

        byte_rate = s.audio_capture.actual_rate * s.audio_capture.actual_channels * 2
        block_align = s.audio_capture.actual_channels * 2
        header = bytearray()
        header.extend(b'RIFF')
        header.extend(struct.pack('<I', 36 + 0x7FFFFFFF))
        header.extend(b'WAVE')
        header.extend(b'fmt ')
        header.extend(struct.pack('<I', 16))
        header.extend(struct.pack('<H', 1))
        header.extend(struct.pack('<H', s.audio_capture.actual_channels))
        header.extend(struct.pack('<I', s.audio_capture.actual_rate))
        header.extend(struct.pack('<I', byte_rate))
        header.extend(struct.pack('<H', block_align))
        header.extend(struct.pack('<H', 16))
        header.extend(b'data')
        header.extend(struct.pack('<I', 0x7FFFFFFF))
        self.wfile.write(bytes(header))

        try:
            while s and s.running and s.audio_capture and s.audio_capture.running:
                try:
                    audio_data = s.audio_capture.audio_queue.get(timeout=2.0)
                    self.wfile.write(audio_data)
                except queue.Empty:
                    silence = b'\x00' * (s.audio_capture.chunk_size * s.audio_capture.actual_channels * 2)
                    self.wfile.write(silence)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            if s:
                s.log(f"Error proxy audio: {e}")

    def send_stream(self, video_only=False):
        s = ScreenStreamHandler.server_instance
        if not s:
            self.send_error(500)
            return

        if s.get_client_count() >= MAX_CLIENTS:
            self.send_response(503)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Max clients reached. Please try again later.")
            return

        self.send_video_only_stream()

    def send_video_only_stream(self):
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
        self.audio_device_index = None
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
                with mss.mss() as sct:
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

    def get_audio_devices(self):
        if not PYAUDIO_AVAILABLE:
            return []
        try:
            audio_cap = VBCableAudioCapture()
            devices = audio_cap.get_input_devices()
            return devices
        except Exception as e:
            print(f"[!] Error obteniendo dispositivos audio: {e}")
        return []

    def add_client(self, address):
        with self.clients_lock:
            if len(self.clients) < MAX_CLIENTS:
                self.clients.add(address)
                self.log(f"[+] Cliente conectado: {address} ({len(self.clients)}/{MAX_CLIENTS})")
            else:
                self.log(f"[!] Cliente rechazado: {address} - Maximo alcanzado ({MAX_CLIENTS})")
        self.gui.update_client_count(len(self.clients))

    def remove_client(self, address):
        with self.clients_lock:
            self.clients.discard(address)
        self.gui.update_client_count(len(self.clients))

    def get_client_count(self):
        with self.clients_lock:
            return len(self.clients)

    def log(self, message):
        self.gui.log(message)

    def start(self, port, quality, fps, ms_interval, private, username, password,
              vlc_mode=False, monitor_idx=1, resolution=None, audio_enabled=False,
              audio_device_index=None):
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
        self.audio_device_index = audio_device_index

        self.screen_capture = ScreenCapture(monitor_idx, resolution)

        if audio_enabled and PYAUDIO_AVAILABLE:
            self.audio_capture = VBCableAudioCapture()
            if self.audio_capture.start(audio_device_index):
                self.log("[+] Captura de audio iniciada")
                self.log(f"    Dispositivo: {audio_device_index}")
                self.log(f"    Puerto dedicado: {self.audio_capture.audio_port}")
                self.log(f"    Frecuencia: {self.audio_capture.actual_rate} Hz")
                self.log(f"    Canales: {self.audio_capture.actual_channels}")
                self.log(f"    URL Audio: http://{self.local_ip}:{self.audio_capture.audio_port}/audio")
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
        audio_url = ""
        audio_html = ""
        if self.audio_enabled and self.audio_capture and self.audio_capture.running:
            audio_url = f"http://{self.local_ip}:{self.audio_capture.audio_port}/audio"
            audio_html = f'''<div class="audio-controls" style="background:#16213e;padding:10px 20px;border-radius:8px;margin:10px 0;text-align:center;">
            <span style="color:#4ecca3;font-size:0.9rem;">&#127911; Audio del sistema disponible</span>
            <audio id="audioPlayer" controls autoplay style="margin-left:15px;vertical-align:middle;width:300px;" src="{audio_url}">
                Tu navegador no soporta audio HTML5.
            </audio>
            <p style="color:#888;font-size:0.8rem;margin-top:5px;">
                Si no escuchas audio, configura VB-CABLE: Panel de Sonido &rarr; Grabaci&oacute;n &rarr; CABLE Output &rarr; Escuchar &rarr; Altavoces
            </p>
        </div>'''

        return f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="icon" type="image/png" href="/favicon.ico">
    <title>Python Screen Task</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background-color: #1a1a2e; color: #eee; min-height: 100vh; display: flex; flex-direction: column; }}
        .header {{ background: linear-gradient(135deg, #16213e 0%, #0f3460 100%); padding: 15px 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.3); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; }}
        .header h1 {{ font-size: 1.5rem; color: #e94560; display: flex; align-items: center; gap: 10px; }}
        .header h1 .icon {{ font-size: 1.8rem; }}
        .nav-links {{ display: flex; gap: 15px; flex-wrap: wrap; }}
        .nav-links a {{ color: #a0a0a0; text-decoration: none; padding: 8px 16px; border-radius: 6px; transition: all 0.3s ease; font-size: 0.9rem; }}
        .nav-links a:hover {{ color: #e94560; background: rgba(233, 69, 96, 0.1); }}
        .nav-links a.active {{ color: #e94560; background: rgba(233, 69, 96, 0.15); }}
        .main-content {{ flex: 1; padding: 20px; display: flex; flex-direction: column; align-items: center; max-width: 1400px; margin: 0 auto; width: 100%; }}
        .status-bar {{ display: flex; align-items: center; gap: 20px; margin-bottom: 15px; padding: 10px 20px; background: #16213e; border-radius: 8px; width: 100%; justify-content: center; flex-wrap: wrap; }}
        .status-indicator {{ display: flex; align-items: center; gap: 8px; }}
        .status-dot {{ width: 10px; height: 10px; border-radius: 50%; background: #4ecca3; animation: pulse 2s infinite; }}
        @keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.5; }} }}
        .status-text {{ font-size: 0.9rem; color: #4ecca3; }}
        .viewer-container {{ width: 100%; background: #0a0a0a; border-radius: 12px; overflow: hidden; box-shadow: 0 8px 32px rgba(0,0,0,0.4); position: relative; border: 2px solid #16213e; }}
        .viewer-container.fullscreen {{ position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; z-index: 9999; border-radius: 0; border: none; }}
        .stream-wrapper {{ position: relative; width: 100%; padding-bottom: 56.25%; background: #000; }}
        .viewer-container.fullscreen .stream-wrapper {{ padding-bottom: 0; height: 100vh; }}
        .stream-image {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; object-fit: contain; background: #000; }}
        .loading-overlay {{ position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; flex-direction: column; justify-content: center; align-items: center; background: rgba(0,0,0,0.8); z-index: 10; transition: opacity 0.3s; }}
        .loading-overlay.hidden {{ opacity: 0; pointer-events: none; }}
        .spinner {{ width: 50px; height: 50px; border: 4px solid #16213e; border-top: 4px solid #e94560; border-radius: 50%; animation: spin 1s linear infinite; }}
        @keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}
        .controls {{ display: flex; justify-content: center; align-items: center; gap: 15px; padding: 15px 20px; background: #16213e; flex-wrap: wrap; }}
        .btn {{ padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9rem; font-weight: 600; display: flex; align-items: center; gap: 8px; transition: all 0.3s ease; }}
        .btn:hover {{ transform: translateY(-2px); box-shadow: 0 4px 12px rgba(0,0,0,0.3); }}
        .btn-success {{ background: #4ecca3; color: #1a1a2e; }}
        .modal-overlay {{ display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; justify-content: center; align-items: center; padding: 20px; }}
        .modal-overlay.visible {{ display: flex; }}
        .modal-content {{ background: #16213e; border-radius: 12px; max-width: 600px; width: 100%; max-height: 80vh; overflow-y: auto; box-shadow: 0 20px 60px rgba(0,0,0,0.5); border: 1px solid #0f3460; }}
        .modal-header {{ padding: 20px; border-bottom: 1px solid #0f3460; display: flex; justify-content: space-between; align-items: center; }}
        .modal-header h2 {{ color: #e94560; font-size: 1.3rem; }}
        .modal-close {{ background: none; border: none; color: #a0a0a0; font-size: 1.5rem; cursor: pointer; }}
        .modal-body {{ padding: 20px; line-height: 1.6; }}
        .modal-body p {{ margin-bottom: 12px; color: #ccc; }}
        .modal-body .highlight {{ color: #4ecca3; font-weight: 600; }}
        .modal-body .project-list {{ margin: 15px 0; padding-left: 20px; }}
        .modal-body .project-list li {{ margin-bottom: 8px; color: #a0a0a0; }}
        .modal-body .project-list a {{ color: #e94560; text-decoration: none; }}
        .footer {{ background: #16213e; padding: 20px; text-align: center; border-top: 1px solid #0f3460; }}
        .footer p {{ color: #888; font-size: 0.85rem; margin-bottom: 5px; }}
        .footer a {{ color: #e94560; text-decoration: none; }}
        .audio-badge {{ background: #4ecca3; color: #1a1a2e; padding: 5px 15px; border-radius: 20px; font-size: 0.85rem; display: inline-block; margin-left: 10px; }}
        @media (max-width: 768px) {{ .header {{ flex-direction: column; text-align: center; }} .controls {{ flex-direction: column; }} }}
    </style>
</head>
<body>
    <header class="header">
        <h1><span class="icon">&#128250;</span>Python Screen Task {'<span class="audio-badge">&#127911; AUDIO ON</span>' if self.audio_enabled else ''}</h1>
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
            {'<div class="status-indicator"><span style="color:#4ecca3;font-size:0.9rem;">&#127911; Audio activo</span></div>' if self.audio_enabled else ''}
        </div>
        {audio_html}
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
                    <li><a href="https://github.com/lgona/ScreenTask" target="_blank">ScreenTask Python (lgona)</a></li>
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
        <p>&copy; Python Screen Task 2026 | <a href="https://github.com/lgona/ScreenTask" target="_blank">lgona</a> Desarrollado por Lenin Ona</p>
    </footer>
    <script>
        let streamImage = document.getElementById('streamImage');
        let loadingOverlay = document.getElementById('loadingOverlay');
        let viewerContainer = document.getElementById('viewerContainer');
        streamImage.onload = function() {{ loadingOverlay.classList.add('hidden'); }};
        streamImage.onerror = function() {{ setTimeout(() => {{ streamImage.src = '/stream?' + Date.now(); }}, 2000); }};
        document.getElementById('btnFullscreen').onclick = function() {{
            if (document.fullscreenElement) {{ document.exitFullscreen(); }} else {{ viewerContainer.requestFullscreen(); }}
        }};
        document.getElementById('lnkAbout').onclick = function(e) {{ e.preventDefault(); document.getElementById('modalAbout').classList.add('visible'); }};
        document.getElementById('closeAbout').onclick = function() {{ document.getElementById('modalAbout').classList.remove('visible'); }};
        document.getElementById('modalAbout').onclick = function(e) {{ if (e.target === this) {{ this.classList.remove('visible'); }} }};
    </script>
</body>
</html>'''

    def generate_vlc_html(self):
        stream_url_video = f"http://{self.local_ip}:{self.port}/stream"
        stream_url_audio = ""
        audio_status = "🔇 Sin audio"
        audio_badge_class = "mute-badge"

        if self.audio_enabled and self.audio_capture and self.audio_capture.running:
            stream_url_audio = f"http://{self.local_ip}:{self.audio_capture.audio_port}/audio"
            audio_status = "✅ Audio disponible en URL separada"
            audio_badge_class = "audio-badge"

        return f'''<!DOCTYPE html>
<html><head><title>VLC Stream - Python Screen Task</title>
<link rel="icon" type="image/png" href="/favicon.ico">
<style>
body {{ background: #1a1a2e; color: #eee; font-family: 'Segoe UI', Arial; text-align: center; padding: 50px; }}
h1 {{ color: #e94560; }} .url-box {{ background: #16213e; padding: 20px; border-radius: 10px; margin: 30px auto; max-width: 700px; border: 2px solid #0f3460; }}
code {{ background: #0a0a0a; padding: 15px 25px; border-radius: 8px; font-size: 1.1rem; color: #4ecca3; display: inline-block; margin: 10px 0; word-break: break-all; }}
.steps {{ text-align: left; max-width: 500px; margin: 20px auto; color: #a0a0a0; }}
.steps li {{ margin: 10px 0; }}
.footer {{ margin-top: 40px; font-size: 0.85rem; color: #888; }}
.audio-badge {{ background: #4ecca3; color: #1a1a2e; padding: 5px 15px; border-radius: 20px; font-size: 0.9rem; display: inline-block; margin: 10px 0; }}
.warning-badge {{ background: #ff9800; color: #1a1a2e; padding: 5px 15px; border-radius: 20px; font-size: 0.9rem; display: inline-block; margin: 10px 0; }}
.mute-badge {{ background: #666; color: #fff; padding: 5px 15px; border-radius: 20px; font-size: 0.9rem; display: inline-block; margin: 10px 0; }}
.limit-info {{ background: #0f3460; padding: 10px; border-radius: 8px; margin: 20px auto; max-width: 400px; font-size: 0.85rem; }}
.alt-url {{ margin-top: 15px; padding-top: 15px; border-top: 1px solid #0f3460; }}
.alt-url p {{ color: #888; font-size: 0.85rem; margin-bottom: 5px; }}
</style></head>
<body>
<h1>&#127909; Transmitiendo a VLC</h1>
<p>El servidor esta en modo VLC. La interfaz web esta deshabilitada.</p>
<div class="url-box">
    <p><strong>URL del stream de VIDEO:</strong></p>
    <code>{stream_url_video}</code>
    <p style="margin-top:15px;color:#888;font-size:0.9rem;">Copia esta URL y pegala en VLC (Video)</p>

    {f'<div class="alt-url"><p><strong>URL del stream de AUDIO:</strong></p><code>{stream_url_audio}</code><p style="margin-top:10px;color:#888;font-size:0.9rem;">En VLC: Agrega esta URL como segunda pista de audio</p></div>' if stream_url_audio else ''}

    <div class="{audio_badge_class}">
        {audio_status}
    </div>
</div>
<div class="steps">
    <p><strong>Pasos en VLC:</strong></p>
    <ol>
        <li>Abre VLC Media Player</li>
        <li>Ve a <strong>Medio &gt; Abrir flujo de red</strong></li>
        <li>Pega la URL de VIDEO de arriba</li>
        {f'<li>Para audio: <strong>Audio &gt; Pista de audio &gt; Agregar pista</strong> y pega la URL de audio</li>' if stream_url_audio else ''}
        <li>Haz clic en <strong>Reproducir</strong></li>
    </ol>
</div>
<div class="limit-info">
    <strong>📊 Límite de clientes: {MAX_CLIENTS} conexiones simultáneas</strong>
</div>
<div class="footer">
    <p>Python Screen Task 2026 | Basado en ScreenTask de Eslam Hamouda y Ahmad Omar</p>
</div>
</body></html>'''


class ScreenTaskGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Screen Task v3.1 - Audio VB-CABLE")
        self.root.geometry("850x750")
        self.root.configure(bg="#2d2d2d")
        self.root.resizable(True, True)

        self.server = ScreenTaskServer(self)
        self.server_running = False

        self.build_ui()

    def build_ui(self):
        header_frame = tk.Frame(self.root, bg="#1a1a2e", height=60)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        tk.Label(header_frame, text="SCREEN TASK", font=('Segoe UI', 20, 'bold'),
                bg="#1a1a2e", fg="#e94560").pack(side=tk.LEFT, padx=20, pady=10)
        tk.Label(header_frame, text="Python Edition 2026 - Audio VB-CABLE", font=('Segoe UI', 10),
                bg="#1a1a2e", fg="#888888").pack(side=tk.LEFT, pady=10)

        red_frame = tk.LabelFrame(self.root, text="Configuracion de Red", bg="#2d2d2d",
                                 fg="#e94560", font=('Segoe UI', 11, 'bold'), padx=10, pady=10)
        red_frame.pack(fill=tk.X, padx=15, pady=5)

        tk.Label(red_frame, text="IP Local:", bg="#2d2d2d", fg="#ffffff",
                font=('Segoe UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)

        self.ip_combo = ttk.Combobox(red_frame, values=self.server.get_all_ips(),
                                     state="readonly", width=25)
        self.ip_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        if self.ip_combo['values']:
            self.ip_combo.current(0)

        tk.Label(red_frame, text="Puerto:", bg="#2d2d2d", fg="#ffffff",
                font=('Segoe UI', 10)).grid(row=0, column=2, sticky=tk.W, padx=(20,0), pady=5)

        self.port_entry = tk.Spinbox(red_frame, from_=1024, to=65535, width=10,
                                     font=('Segoe UI', 10), value=DEFAULT_PORT)
        self.port_entry.grid(row=0, column=3, sticky=tk.W, padx=5, pady=5)

        tk.Label(red_frame, text="URL Video:", bg="#2d2d2d", fg="#ffffff",
                font=('Segoe UI', 10)).grid(row=1, column=0, sticky=tk.W, pady=5)

        self.url_entry = tk.Entry(red_frame, font=('Segoe UI', 10), width=45,
                                 bg="#1a1a2e", fg="#4ecca3", insertbackground="#ffffff")
        self.url_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        self.update_url()

        self.btn_open_browser = tk.Button(red_frame, text="Abrir Navegador",
                                         command=self.open_browser, bg="#0f3460", fg="#ffffff",
                                         font=('Segoe UI', 9), padx=10)
        self.btn_open_browser.grid(row=1, column=3, padx=5, pady=5)

        btn_frame = tk.Frame(self.root, bg="#2d2d2d")
        btn_frame.pack(fill=tk.X, padx=15, pady=5)

        self.btn_start = tk.Button(btn_frame, text="INICIAR SERVIDOR", command=self.start_server,
                                  bg="#4ecca3", fg="#1a1a2e", font=('Segoe UI', 12, 'bold'),
                                  padx=25, pady=8, cursor="hand2")
        self.btn_start.pack(side=tk.LEFT, padx=5)

        self.btn_stop = tk.Button(btn_frame, text="DETENER SERVIDOR", command=self.stop_server,
                                 bg="#e94560", fg="#ffffff", font=('Segoe UI', 12, 'bold'),
                                 padx=25, pady=8, cursor="hand2", state="disabled")
        self.btn_stop.pack(side=tk.LEFT, padx=5)

        self.btn_vlc = tk.Button(btn_frame, text="TRANSMITIR A VLC", command=self.start_vlc_mode,
                                bg="#0f3460", fg="#ffffff", font=('Segoe UI', 12, 'bold'),
                                padx=20, pady=8, cursor="hand2")
        self.btn_vlc.pack(side=tk.RIGHT, padx=5)

        self.client_label = tk.Label(self.root, text=f"Clientes conectados: 0 / {MAX_CLIENTS}",
                                    bg="#2d2d2d", fg="#4ecca3", font=('Segoe UI', 11, 'bold'))
        self.client_label.pack(pady=5)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background="#2d2d2d", tabmargins=[2, 5, 2, 0])
        style.configure("TNotebook.Tab", background="#1a1a2e", foreground="#ffffff",
                       font=('Segoe UI', 10), padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", "#0f3460")],
                 foreground=[("selected", "#e94560")])

        tab1 = tk.Frame(self.notebook, bg="#2d2d2d")
        self.notebook.add(tab1, text="Calidad, Monitor y Privacidad")

        monitor_frame = tk.LabelFrame(tab1, text="Pantalla", bg="#2d2d2d",
                                     fg="#e94560", font=('Segoe UI', 10, 'bold'), padx=10, pady=10)
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

        quality_frame = tk.LabelFrame(tab1, text="Calidad y Velocidad", bg="#2d2d2d",
                                     fg="#e94560", font=('Segoe UI', 10, 'bold'), padx=10, pady=10)
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

        priv_frame = tk.LabelFrame(tab1, text="Privacidad", bg="#2d2d2d",
                                  fg="#e94560", font=('Segoe UI', 10, 'bold'), padx=10, pady=10)
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

        tab2 = tk.Frame(self.notebook, bg="#2d2d2d")
        self.notebook.add(tab2, text="Consola de Mensajes")

        console_frame = tk.LabelFrame(tab2, text="Log del Servidor", bg="#2d2d2d",
                                     fg="#e94560", font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        console_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.console = scrolledtext.ScrolledText(console_frame, wrap=tk.WORD,
                                                 font=('Consolas', 9), bg="#0a0a0a",
                                                 fg="#4ecca3", insertbackground="#ffffff",
                                                 state="disabled", height=15)
        self.console.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tab3 = tk.Frame(self.notebook, bg="#2d2d2d")
        self.notebook.add(tab3, text="Configuracion de Audio")

        if not PYAUDIO_AVAILABLE:
            tk.Label(tab3, text="❌ PyAudio no instalado. Ejecuta: pip install PyAudioWPatch",
                    bg="#2d2d2d", fg="#ff6b6b", font=('Segoe UI', 11, 'bold')).pack(pady=20)
        else:
            info_vb = tk.LabelFrame(tab3, text="Guia de Configuracion VB-CABLE", bg="#2d2d2d",
                                   fg="#e94560", font=('Segoe UI', 10, 'bold'), padx=10, pady=10)
            info_vb.pack(fill=tk.X, padx=10, pady=5)

            guia_text = """1. Descarga e instala VB-CABLE desde: https://vb-audio.com/Cable/
2. Ve a Panel de Control -> Sonido -> Grabacion
3. Habilita "CABLE Output (VB-Audio Virtual Cable)"
4. Clic derecho -> Propiedades -> Escuchar -> Marca "Escuchar este dispositivo"
5. Selecciona tus altavoces en "Reproducir a traves de"
6. El audio de tu PC ahora se redirige a VB-CABLE y se captura por este servidor"""

            tk.Label(info_vb, text=guia_text, bg="#2d2d2d", fg="#cccccc",
                    font=('Segoe UI', 9), justify=tk.LEFT, wraplength=700).pack(anchor=tk.W, pady=5)

            devices_frame = tk.LabelFrame(tab3, text="Dispositivos de Entrada de Audio",
                                         bg="#2d2d2d", fg="#e94560", font=('Segoe UI', 10, 'bold'),
                                         padx=10, pady=10)
            devices_frame.pack(fill=tk.X, padx=10, pady=5)

            tk.Label(devices_frame, text="Dispositivo de captura:", bg="#2d2d2d", fg="#ffffff",
                    font=('Segoe UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)

            audio_devices = self.server.get_audio_devices()
            device_names = []
            vb_found = False
            for d in audio_devices:
                vb_marker = " 🎧 VB-CABLE" if any(x in d['name'].lower() for x in ['vb-audio', 'cable', 'virtual']) else ""
                if vb_marker:
                    vb_found = True
                device_names.append(f"{d['index']}: {d['name']}{vb_marker}")

            if not device_names:
                device_names = ["No se encontraron dispositivos de entrada"]

            self.audio_device_combo = ttk.Combobox(devices_frame, values=device_names,
                                                   state="readonly" if audio_devices else "disabled",
                                                   width=55)
            self.audio_device_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

            if audio_devices:
                vb_idx = 0
                for i, d in enumerate(audio_devices):
                    if any(x in d['name'].lower() for x in ['vb-audio', 'cable', 'virtual']):
                        vb_idx = i
                        break
                self.audio_device_combo.current(vb_idx)

            self.btn_refresh_audio = tk.Button(devices_frame, text="Refrescar",
                                              command=self.refresh_audio_devices,
                                              bg="#0f3460", fg="#ffffff", font=('Segoe UI', 9))
            self.btn_refresh_audio.grid(row=0, column=2, padx=5, pady=5)

            if vb_found:
                tk.Label(devices_frame, text="✅ VB-CABLE detectado", bg="#2d2d2d", fg="#4ecca3",
                        font=('Segoe UI', 9, 'bold')).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)
            else:
                tk.Label(devices_frame, text="⚠️ VB-CABLE no detectado. Selecciona otro dispositivo de entrada.",
                        bg="#2d2d2d", fg="#ff9800", font=('Segoe UI', 9)).grid(row=1, column=0, columnspan=3, sticky=tk.W, pady=5)

            options_frame = tk.LabelFrame(tab3, text="Opciones de Audio", bg="#2d2d2d",
                                         fg="#e94560", font=('Segoe UI', 10, 'bold'), padx=10, pady=10)
            options_frame.pack(fill=tk.X, padx=10, pady=5)

            self.audio_enabled_var = tk.BooleanVar(value=False)
            self.chk_audio = tk.Checkbutton(options_frame, text="Habilitar captura de audio del sistema (VB-CABLE / Dispositivo de entrada)",
                                           variable=self.audio_enabled_var, bg="#2d2d2d", fg="#ffffff",
                                           selectcolor="#1a1a2e", activebackground="#2d2d2d",
                                           activeforeground="#ffffff", font=('Segoe UI', 10))
            self.chk_audio.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)

            tk.Label(options_frame, text="Puerto de audio dedicado:", bg="#2d2d2d", fg="#888888",
                    font=('Segoe UI', 10)).grid(row=1, column=0, sticky=tk.W, pady=5)
            self.audio_port_label = tk.Label(options_frame, text=str(AUDIO_PORT), bg="#2d2d2d", fg="#4ecca3",
                                            font=('Segoe UI', 10, 'bold'))
            self.audio_port_label.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)

            info_text = f"""Notas importantes:
- El audio se captura del dispositivo de ENTRADA seleccionado (microfono, VB-CABLE, Stereo Mix, etc.)
- NO requiere ffmpeg ni pydub - El audio se sirve como WAV directamente
- El audio tiene su propio servidor HTTP en el puerto {AUDIO_PORT}
- Desde la web: El navegador reproduce audio automaticamente via <audio> tag
- Desde VLC: Usa la URL de video + la URL de audio como pistas separadas
- Límite máximo de clientes concurrentes: {MAX_CLIENTS}"""

            tk.Label(tab3, text=info_text, bg="#2d2d2d", fg="#888888",
                    font=('Segoe UI', 9), justify=tk.LEFT, wraplength=700).pack(pady=10, padx=10)

        footer = tk.Frame(self.root, bg="#1a1a2e", height=30)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        tk.Label(footer, text="Python Screen Task 2026 | Basado en ScreenTask de Eslam Hamouda y Ahmad Omar",
                bg="#1a1a2e", fg="#888888", font=('Segoe UI', 8)).pack(pady=5)

        self.ip_combo.bind("<<ComboboxSelected>>", lambda e: self.update_url())
        self.port_entry.bind("<KeyRelease>", lambda e: self.update_url())

    def refresh_audio_devices(self):
        audio_devices = self.server.get_audio_devices()
        device_names = []
        for d in audio_devices:
            vb_marker = " 🎧 VB-CABLE" if any(x in d['name'].lower() for x in ['vb-audio', 'cable', 'virtual']) else ""
            device_names.append(f"{d['index']}: {d['name']}{vb_marker}")

        if not device_names:
            device_names = ["No se encontraron dispositivos de entrada"]

        self.audio_device_combo['values'] = device_names
        if audio_devices:
            vb_idx = 0
            for i, d in enumerate(audio_devices):
                if any(x in d['name'].lower() for x in ['vb-audio', 'cable', 'virtual']):
                    vb_idx = i
                    break
            self.audio_device_combo.current(vb_idx)
            self.audio_device_combo.config(state="readonly")
        else:
            self.audio_device_combo.config(state="disabled")
        self.log(f"Dispositivos de audio actualizados: {len(audio_devices)} encontrados")

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
        self.client_label.config(text=f"Clientes conectados: {count} / {MAX_CLIENTS}")

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

    def get_audio_device_index(self):
        if not hasattr(self, 'audio_device_combo'):
            return None
        selected = self.audio_device_combo.get()
        if selected and ':' in selected:
            try:
                return int(selected.split(':')[0])
            except:
                pass
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

            audio_enabled = False
            audio_device_index = None
            if hasattr(self, 'audio_enabled_var') and self.audio_enabled_var.get():
                audio_enabled = True
                audio_device_index = self.get_audio_device_index()

            self.log(f"Iniciando servidor en puerto {port}...")
            self.log(f"Límite de clientes: {MAX_CLIENTS} conexiones simultáneas")

            if self.server.start(port, quality, fps, ms_interval, private, username, password,
                                vlc_mode, monitor_idx, resolution, audio_enabled, audio_device_index):
                self.server_running = True
                self.btn_start.config(state="disabled")
                self.btn_stop.config(state="normal")
                self.btn_vlc.config(state="disabled")

                mode_text = "MODO VLC" if vlc_mode else "modo Web"
                self.log(f"Servidor iniciado correctamente en {mode_text}")
                self.log(f"URL Web: http://{self.server.local_ip}:{port}")
                self.log(f"URL Stream Video: http://{self.server.local_ip}:{port}/stream")
                self.log(f"Calidad: {quality} | MS: {ms_interval}ms | FPS: {fps}")
                self.log(f"Monitor: {self.monitor_combo.get()}")
                if resolution:
                    self.log(f"Resolucion de salida: {resolution[0]}x{resolution[1]}")

                if private:
                    self.log("Modo privado activado - Se requiere autenticacion")

                if audio_enabled:
                    self.log("[+] Audio del sistema activado (VB-CABLE)")
                    if hasattr(self, 'audio_device_combo'):
                        self.log(f"    Dispositivo: {self.audio_device_combo.get()}")
                    self.log(f"    URL Audio: http://{self.server.local_ip}:{AUDIO_PORT}/audio")
                    self.log("    Formato: WAV PCM 16-bit (sin compresion)")

                if vlc_mode:
                    self.log("=" * 50)
                    self.log("MODO VLC ACTIVADO")
                    self.log("=" * 50)

                    vlc_url = f"http://{self.server.local_ip}:{port}/stream"
                    msg = f"Servidor VLC activo.\n\nURL Video: {vlc_url}"
                    if audio_enabled and self.server.audio_capture and self.server.audio_capture.running:
                        audio_url = f"http://{self.server.local_ip}:{AUDIO_PORT}/audio"
                        msg += f"\n\nURL Audio: {audio_url}"
                        msg += "\n\nEn VLC: Agrega la URL de audio como segunda pista"
                    msg += "\n\nAbrir en VLC: Medio > Abrir flujo de red"

                    messagebox.showinfo("Modo VLC", msg)
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
