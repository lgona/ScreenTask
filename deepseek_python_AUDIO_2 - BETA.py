# Python Screen Task v3.0 - Interfaz Grafica Final
# Basado en ScreenTask de Eslam Hamouda y Ahmad Omar
# Version Python GUI por Lenin Ona - 2026
# Mejoras: Pestañas, Audio WASAPI Loopback, Favicon, Sincronizacion A/V, MP3 Audio

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

# Importar para MP3 encoding
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    print("[!] Instala pydub: pip install pydub")
    print("[!] Tambien necesitas ffmpeg: https://ffmpeg.org/download.html")

from PIL import Image
from http.server import BaseHTTPRequestHandler, HTTPServer

# ==================== CONFIGURACION GLOBAL ====================
DEFAULT_PORT = 8080
DEFAULT_QUALITY = 55
DEFAULT_FPS = 25
DEFAULT_MS = 40
MAX_CLIENTS = 5  # Limite de clientes conectados
FAVICON_PATH = "favicon.png"
# =============================================================

def check_ffmpeg():
    """Verifica si ffmpeg está disponible en el sistema"""
    try:
        # Buscar ffmpeg en diferentes ubicaciones comunes
        ffmpeg_paths = [
            "ffmpeg",  # En PATH
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]
        
        for path in ffmpeg_paths:
            try:
                result = subprocess.run([path, "-version"], capture_output=True, text=True)
                if result.returncode == 0:
                    return True
            except:
                continue
        return False
    except:
        return False

FFMPEG_AVAILABLE = check_ffmpeg()

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

class AudioCaptureWASAPI:
    """Captura audio del sistema usando WASAPI loopback (Windows 10/11)"""

    def __init__(self, device_index=None, sample_rate=44100, channels=2, chunk_size=1024):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_size = chunk_size
        self.running = False
        self.audio_queue = deque(maxlen=500)  # Buffer circular para sincronizacion
        self.stream = None
        self.pa = None
        self.lock = threading.Lock()
        self.last_mp3_frame = None
        self.actual_channels = 2
        self.actual_rate = 44100

    def get_wasapi_devices(self):
        """Obtiene lista de dispositivos WASAPI con loopback disponibles"""
        devices = []
        if not PYAUDIO_AVAILABLE:
            return devices
        try:
            pa_temp = pyaudio.PyAudio()
            default_output = None
            try:
                default_output = pa_temp.get_default_output_device_info()
            except:
                pass
            
            for i in range(pa_temp.get_device_count()):
                try:
                    info = pa_temp.get_device_info_by_index(i)
                    # Verificar si es dispositivo WASAPI y de salida
                    host_api_info = pa_temp.get_host_api_info_by_index(info['hostApi'])
                    if 'WASAPI' in host_api_info['name'] and info.get('maxOutputChannels', 0) > 0:
                        is_default = False
                        if default_output and default_output.get('index') == i:
                            is_default = True
                        
                        # Determinar canales soportados
                        max_channels = int(info.get('maxOutputChannels', 2))
                        supported_channels = min(max_channels, 2)
                        
                        devices.append({
                            'index': i,
                            'name': info.get('name', 'Unknown'),
                            'channels': supported_channels,
                            'rate': int(info.get('defaultSampleRate', 44100)),
                            'is_default': is_default,
                            'max_channels': max_channels
                        })
                except Exception as e:
                    continue
                    
            pa_temp.terminate()
        except Exception as e:
            print(f"[!] Error listando dispositivos: {e}")
        return devices

    def start(self, device_index=None):
        if not PYAUDIO_AVAILABLE:
            return False
        
        with self.lock:
            self.audio_queue.clear()
        
        try:
            self.pa = pyaudio.PyAudio()

            if device_index is not None:
                self.device_index = device_index
            elif self.device_index is None:
                try:
                    default_info = self.pa.get_default_output_device_info()
                    self.device_index = default_info['index']
                except:
                    return False

            device_info = self.pa.get_device_info_by_index(self.device_index)
            self.actual_rate = int(device_info.get('defaultSampleRate', 44100))
            max_channels = int(device_info.get('maxOutputChannels', 2))
            self.actual_channels = min(max_channels, 2)
            
            print(f"[DEBUG] Dispositivo: {device_info.get('name')}")
            print(f"[DEBUG] Canales: {self.actual_channels}, Rate: {self.actual_rate}")
            
            # HACK para PyAudio normal: usar output=True con input_device_index
            # Esto fuerza el modo loopback en algunos drivers WASAPI
            try:
                self.stream = self.pa.open(
                    format=pyaudio.paInt16,
                    channels=self.actual_channels,
                    rate=self.actual_rate,
                    input=True,
                    output=False,
                    input_device_index=self.device_index,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=self._audio_callback
                )
            except Exception as e1:
                print(f"[DEBUG] Fallo input directo: {e1}")
                # Ultimo recurso: usar Stereo Mix si existe
                stereo_mix = self._find_stereo_mix()
                if stereo_mix is not None:
                    self.device_index = stereo_mix
                    self.actual_rate = 44100
                    self.actual_channels = 2
                    self.stream = self.pa.open(
                        format=pyaudio.paInt16,
                        channels=2,
                        rate=44100,
                        input=True,
                        input_device_index=stereo_mix,
                        frames_per_buffer=self.chunk_size,
                        stream_callback=self._audio_callback
                    )
                    print(f"[DEBUG] Usando Stereo Mix como fallback")
                else:
                    raise

            self.running = True
            self.stream.start_stream()
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

    def _find_stereo_mix(self):
        """Busca dispositivo Stereo Mix como fallback"""
        try:
            for i in range(self.pa.get_device_count()):
                info = self.pa.get_device_info_by_index(i)
                name = info.get('name', '').lower()
                if 'stereo mix' in name or 'what u hear' in name or 'mezcla estereo' in name:
                    return i
        except:
            pass
        return None
        
    def _audio_callback(self, in_data, frame_count, time_info, status):
        if self.running and in_data:
            with self.lock:
                self.audio_queue.append(in_data)
        return (None, pyaudio.paContinue)

    def get_audio_frame(self):
        with self.lock:
            if len(self.audio_queue) > 0:
                return self.audio_queue.popleft()
        return None

    def get_audio_buffer_size(self):
        with self.lock:
            return len(self.audio_queue)

    def get_mp3_frame(self, duration_ms=40):
        """Convierte el audio acumulado a MP3 si ffmpeg está disponible"""
        if not PYDUB_AVAILABLE or not FFMPEG_AVAILABLE:
            return None
        
        with self.lock:
            if len(self.audio_queue) == 0:
                return self.last_mp3_frame
            
            # Recopilar datos de audio
            audio_data = b''
            chunks_to_take = min(len(self.audio_queue), 10)  # Limitar chunks
            for _ in range(chunks_to_take):
                if self.audio_queue:
                    audio_data += self.audio_queue.popleft()
        
        if len(audio_data) == 0:
            return self.last_mp3_frame
        
        try:
            # Calcular duración aproximada
            bytes_per_second = self.actual_rate * self.actual_channels * 2  # 16-bit = 2 bytes
            duration = len(audio_data) / bytes_per_second * 1000  # en ms
            
            if duration < 10:  # Muy poco audio
                return self.last_mp3_frame
            
            # Convertir a AudioSegment
            audio_segment = AudioSegment(
                data=audio_data,
                sample_width=2,  # 16-bit = 2 bytes
                frame_rate=self.actual_rate,
                channels=self.actual_channels
            )
            
            # Exportar a MP3
            mp3_buffer = io.BytesIO()
            audio_segment.export(mp3_buffer, format="mp3", bitrate="128k", parameters=["-ac", "2"])
            mp3_buffer.seek(0)
            self.last_mp3_frame = mp3_buffer.read()
            return self.last_mp3_frame
        except Exception as e:
            print(f"[!] Error convirtiendo a MP3: {e}")
            return self.last_mp3_frame

    def stop(self):
        self.running = False
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
        with self.lock:
            self.audio_queue.clear()
            self.last_mp3_frame = None

class ScreenStreamHandler(BaseHTTPRequestHandler):
    server_instance = None

    def do_GET(self):
        # Favicon
        if self.path == '/favicon.ico':
            self.send_favicon()
            return

        # Verificar autenticacion si esta activa
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
            # Stream MJPEG puro (sin audio)
            self.send_stream()

        elif self.path == '/stream.ts':
            # CORRECCION: Verificar que audio este habilitado Y captura exista
            # El flag running puede no estar listo inmediatamente, verificar solo si existe
            if s and s.audio_enabled and s.audio_capture:
                # CORRECCION: No verificar s.audio_capture.running aqui
                # El stream puede iniciarse justo cuando llega la peticion
                self.send_stream_ts()
            else:
                self.send_error(404, "Audio no disponible. Usa /stream para video solo.")

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

    def send_stream(self, video_only=False):
        s = ScreenStreamHandler.server_instance
        if not s:
            self.send_error(500)
            return

        # Verificar límite de clientes
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

    def send_stream_ts(self):
        """Stream MPEG-TS con audio MP3 multiplexado usando ffmpeg"""
        s = ScreenStreamHandler.server_instance
        if not s:
            self.send_error(500)
            return

        # Verificar límite de clientes
        if s.get_client_count() >= MAX_CLIENTS:
            self.send_response(503)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            self.wfile.write(b"Max clients reached. Please try again later.")
            return

        if not FFMPEG_AVAILABLE:
            self.send_error(503, "ffmpeg no disponible para multiplexar audio")
            return

        # CORRECCION: Esperar a que audio_capture este listo (max 3 segundos)
        import time
        wait_count = 0
        while s.audio_capture and not s.audio_capture.running and wait_count < 30:
            time.sleep(0.1)
            wait_count += 1
        
        if not s.audio_capture or not s.audio_capture.running:
            self.send_error(503, "Audio aun no iniciado. Intenta de nuevo.")
            return

        self.send_response(200)
        self.send_header('Content-type', 'video/mp2t')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        s.add_client(self.client_address)
        s.log(f"[+] Cliente TS conectado: {self.client_address} (audio+video)")

        # ... resto del método igual ...

        # Crear pipes para comunicación con ffmpeg
        video_pipe_r, video_pipe_w = os.pipe()
        audio_pipe_r, audio_pipe_w = os.pipe()

        # Comando ffmpeg para multiplexar video MJPEG + audio PCM -> MPEG-TS
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",  # Sobrescribir sin preguntar
            "-f", "image2pipe",
            "-vcodec", "mjpeg",
            "-framerate", str(s.fps),
            "-i", f"pipe:{video_pipe_r}",  # Video desde pipe
            
            "-f", "s16le",
            "-acodec", "pcm_s16le",
            "-ar", str(s.audio_capture.actual_rate),
            "-ac", str(s.audio_capture.actual_channels),
            "-i", f"pipe:{audio_pipe_r}",  # Audio desde pipe
            
            "-c:v", "copy",  # Copiar video MJPEG sin recodificar
            "-c:a", "libmp3lame",  # Codificar audio a MP3
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            
            "-f", "mpegts",  # Formato de salida MPEG-TS
            "-muxdelay", "0",
            "-muxpreload", "0",
            "-fflags", "nobuffer",
            "pipe:1"  # Salida a stdout
        ]

        ffmpeg_process = None

        try:
            # Iniciar ffmpeg
            ffmpeg_process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                pass_fds=(video_pipe_r, audio_pipe_r)
            )

            # Cerrar extremos de lectura en este proceso (ffmpeg los usa)
            os.close(video_pipe_r)
            os.close(audio_pipe_r)

            # Hilos para alimentar ffmpeg
            stop_event = threading.Event()
            video_thread = threading.Thread(
                target=self._feed_video_to_ffmpeg,
                args=(video_pipe_w, s, stop_event),
                daemon=True
            )
            audio_thread = threading.Thread(
                target=self._feed_audio_to_ffmpeg,
                args=(audio_pipe_w, s, stop_event),
                daemon=True
            )

            video_thread.start()
            audio_thread.start()

            # Leer salida de ffmpeg y enviar al cliente
            while s and s.running and not stop_event.is_set():
                chunk = ffmpeg_process.stdout.read(8192)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()

        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass
        except Exception as e:
            s.log(f"Error stream TS: {e}")
        finally:
            stop_event.set()
            video_thread.join(timeout=1)
            audio_thread.join(timeout=1)
            
            try:
                os.close(video_pipe_w)
            except:
                pass
            try:
                os.close(audio_pipe_w)
            except:
                pass
            
            if ffmpeg_process:
                try:
                    ffmpeg_process.terminate()
                    ffmpeg_process.wait(timeout=2)
                except:
                    try:
                        ffmpeg_process.kill()
                    except:
                        pass
            
            s.remove_client(self.client_address)
            s.log(f"[-] Cliente TS desconectado: {self.client_address}")

    def _feed_video_to_ffmpeg(self, pipe_w, server, stop_event):
        """Hilo que alimenta frames de video a ffmpeg"""
        try:
            while server and server.running and not stop_event.is_set():
                try:
                    screenshot = server.screen_capture.capture()
                    img_byte_arr = io.BytesIO()
                    screenshot.save(img_byte_arr, format='JPEG', quality=server.quality, optimize=True)
                    img_data = img_byte_arr.getvalue()
                    
                    os.write(pipe_w, img_data)
                    time.sleep(server.ms_interval / 1000.0)
                    
                except (BrokenPipeError, OSError):
                    break
                except Exception as e:
                    server.log(f"Error feed video: {e}")
                    time.sleep(0.1)
        finally:
            try:
                os.close(pipe_w)
            except:
                pass

    def _feed_audio_to_ffmpeg(self, pipe_w, server, stop_event):
        """Hilo que alimenta audio PCM a ffmpeg"""
        try:
            while server and server.running and not stop_event.is_set():
                try:
                    audio_frame = server.audio_capture.get_audio_frame()
                    if audio_frame:
                        os.write(pipe_w, audio_frame)
                    else:
                        # Escribir silencio si no hay audio para mantener sync
                        silence = b'\x00' * (server.audio_capture.chunk_size * 
                                            server.audio_capture.actual_channels * 2)
                        os.write(pipe_w, silence)
                        time.sleep(0.01)
                        
                except (BrokenPipeError, OSError):
                    break
                except Exception as e:
                    server.log(f"Error feed audio: {e}")
                    time.sleep(0.1)
        finally:
            try:
                os.close(pipe_w)
            except:
                pass

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

    def get_audio_devices(self):
        """Obtiene dispositivos de audio WASAPI disponibles (dispositivos de salida)"""
        if not PYAUDIO_AVAILABLE:
            return []
        try:
            audio_cap = AudioCaptureWASAPI()
            devices = audio_cap.get_wasapi_devices()
            return devices
        except Exception as e:
            print(f"[!] Error obteniendo dispositivos audio: {e}")
        return []

    def get_audio_default_device(self):
        """Obtiene el dispositivo de audio por defecto"""
        devices = self.get_audio_devices()
        for device in devices:
            if device.get('is_default', False):
                return device
        return devices[0] if devices else None

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

        # Iniciar captura de audio si esta habilitado y es modo VLC
        if audio_enabled and vlc_mode and PYAUDIO_AVAILABLE:
            # Si no se especifico dispositivo, usar el predeterminado
            if audio_device_index is None:
                default_device = self.get_audio_default_device()
                if default_device:
                    audio_device_index = default_device['index']
                    self.log(f"[+] Usando dispositivo predeterminado: {default_device['name']}")
            
            if audio_device_index is not None:
                self.audio_capture = AudioCaptureWASAPI(device_index=audio_device_index)
                if self.audio_capture.start(audio_device_index):
                    self.log("[+] Captura de audio WASAPI iniciada")
                    self.log(f"    Dispositivo: {audio_device_index}")
                    self.log(f"    Frecuencia: {self.audio_capture.actual_rate} Hz")
                    self.log(f"    Canales: {self.audio_capture.actual_channels}")
                    
                    if not PYDUB_AVAILABLE:
                        self.log("[!] ADVERTENCIA: pydub no instalado - El audio no se convertira a MP3")
                        self.log("    Ejecuta: pip install pydub")
                    elif not FFMPEG_AVAILABLE:
                        self.log("[!] ADVERTENCIA: ffmpeg no encontrado - El audio no se multiplexara en TS")
                        self.log("    Instala ffmpeg desde: https://ffmpeg.org/download.html")
                        self.log("    O usa: winget install ffmpeg")
                    else:
                        self.log("[+] Audio MPEG-TS disponible en /stream.ts")
                else:
                    self.log("[!] No se pudo iniciar captura de audio")
                    self.audio_capture = None
            else:
                self.log("[!] No se encontro dispositivo de audio valido")
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
    <link rel="icon" type="image/png" href="/favicon.ico">
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
        audio_status = ""
        stream_url_video = f"http://{self.local_ip}:{self.port}/stream"
        stream_url_ts = f"http://{self.local_ip}:{self.port}/stream.ts"
        
        if self.audio_enabled and PYDUB_AVAILABLE and FFMPEG_AVAILABLE:
            audio_status = "✅ Audio MP3 incluido"
            primary_url = stream_url_ts
            url_label = "URL del stream (Video + Audio MP3):"
        elif self.audio_enabled:
            audio_status = "⚠️ Audio disponible (sin MP3 - instala ffmpeg)"
            primary_url = stream_url_video
            url_label = "URL del stream (Solo Video - ffmpeg no disponible):"
        else:
            audio_status = "🔇 Solo video"
            primary_url = stream_url_video
            url_label = "URL del stream (Solo Video):"
            
        return f"""<!DOCTYPE html>
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
    <p><strong>{url_label}</strong></p>
    <code>{primary_url}</code>
    <p style="margin-top:15px;color:#888;font-size:0.9rem;">Copia esta URL y pegala en VLC</p>
    <div class="{'audio-badge' if self.audio_enabled and PYDUB_AVAILABLE and FFMPEG_AVAILABLE else ('warning-badge' if self.audio_enabled else 'mute-badge')}">
        {audio_status}
    </div>
    {f'<div class="alt-url"><p>URL alternativa (solo video):</p><code style="font-size:0.9rem;">{stream_url_video}</code></div>' if self.audio_enabled and PYDUB_AVAILABLE and FFMPEG_AVAILABLE else ''}
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
<div class="limit-info">
    <strong>📊 Límite de clientes: {MAX_CLIENTS} conexiones simultáneas</strong>
</div>
<div class="footer">
    <p>Python Screen Task 2026 | Basado en ScreenTask de Eslam Hamouda y Ahmad Omar</p>
</div>
</body></html>"""

class ScreenTaskGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Python Screen Task v3.0")
        self.root.geometry("800x700")
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

        # ===== PANEL SUPERIOR: Configuracion de Red (siempre visible) =====
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

        tk.Label(red_frame, text="URL:", bg="#2d2d2d", fg="#ffffff", 
                font=('Segoe UI', 10)).grid(row=1, column=0, sticky=tk.W, pady=5)

        self.url_entry = tk.Entry(red_frame, font=('Segoe UI', 10), width=45, 
                                 bg="#1a1a2e", fg="#4ecca3", insertbackground="#ffffff")
        self.url_entry.grid(row=1, column=1, columnspan=2, sticky=tk.W, padx=5, pady=5)
        self.update_url()

        self.btn_open_browser = tk.Button(red_frame, text="Abrir Navegador", 
                                         command=self.open_browser, bg="#0f3460", fg="#ffffff",
                                         font=('Segoe UI', 9), padx=10)
        self.btn_open_browser.grid(row=1, column=3, padx=5, pady=5)

        # ===== BOTONES DE CONTROL (siempre visibles) =====
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

        # ===== CONTADOR DE CLIENTES =====
        self.client_label = tk.Label(self.root, text=f"Clientes conectados: 0 / {MAX_CLIENTS}", 
                                    bg="#2d2d2d", fg="#4ecca3", font=('Segoe UI', 11, 'bold'))
        self.client_label.pack(pady=5)

        # ===== NOTEBOOK (PESTAÑAS) =====
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # Estilo para notebook
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background="#2d2d2d", tabmargins=[2, 5, 2, 0])
        style.configure("TNotebook.Tab", background="#1a1a2e", foreground="#ffffff", 
                       font=('Segoe UI', 10), padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", "#0f3460")], 
                 foreground=[("selected", "#e94560")])

        # --- PESTAÑA 1: Calidad, Monitor y Privacidad ---
        tab1 = tk.Frame(self.notebook, bg="#2d2d2d")
        self.notebook.add(tab1, text="Calidad, Monitor y Privacidad")

        # Monitor
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

        # Calidad
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

        # Privacidad
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

        # --- PESTAÑA 2: Consola de Mensajes ---
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

        # --- PESTAÑA 3: Configuracion de Audio ---
        tab3 = tk.Frame(self.notebook, bg="#2d2d2d")
        self.notebook.add(tab3, text="Configuracion de Audio")

        audio_info = tk.Label(tab3, text="Audio disponible en modo VLC - Selecciona dispositivo de salida", 
                             bg="#2d2d2d", fg="#e94560", font=('Segoe UI', 10, 'bold'))
        audio_info.pack(pady=10)

        # Estado de PyAudioWPatch
        if not PYAUDIO_AVAILABLE:
            tk.Label(tab3, text="❌ PyAudioWPatch no instalado. Ejecuta: pip install PyAudioWPatch", 
                    bg="#2d2d2d", fg="#ff6b6b", font=('Segoe UI', 10)).pack(pady=10)
        else:
            # Dispositivos de audio
            devices_frame = tk.LabelFrame(tab3, text="Dispositivos de Audio de Salida (WASAPI Loopback)", 
                                         bg="#2d2d2d", fg="#e94560", font=('Segoe UI', 10, 'bold'), 
                                         padx=10, pady=10)
            devices_frame.pack(fill=tk.X, padx=10, pady=5)

            tk.Label(devices_frame, text="Dispositivo de salida:", bg="#2d2d2d", fg="#ffffff", 
                    font=('Segoe UI', 10)).grid(row=0, column=0, sticky=tk.W, pady=5)

            # Obtener dispositivos
            audio_devices = self.server.get_audio_devices()
            device_names = []
            for d in audio_devices:
                default_marker = " (PREDETERMINADO)" if d.get('is_default', False) else ""
                device_names.append(f"{d['index']}: {d['name']}{default_marker}")

            if not device_names:
                device_names = ["No se encontraron dispositivos WASAPI"]

            self.audio_device_combo = ttk.Combobox(devices_frame, values=device_names, 
                                                   state="readonly" if audio_devices else "disabled", 
                                                   width=55)
            self.audio_device_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
            if audio_devices:
                # Seleccionar dispositivo predeterminado si existe
                default_idx = 0
                for i, d in enumerate(audio_devices):
                    if d.get('is_default', False):
                        default_idx = i
                        break
                self.audio_device_combo.current(default_idx)

            self.btn_refresh_audio = tk.Button(devices_frame, text="Refrescar", 
                                              command=self.refresh_audio_devices,
                                              bg="#0f3460", fg="#ffffff", font=('Segoe UI', 9))
            self.btn_refresh_audio.grid(row=0, column=2, padx=5, pady=5)

            # Opciones de audio
            options_frame = tk.LabelFrame(tab3, text="Opciones de Audio", bg="#2d2d2d", 
                                         fg="#e94560", font=('Segoe UI', 10, 'bold'), padx=10, pady=10)
            options_frame.pack(fill=tk.X, padx=10, pady=5)

            self.audio_enabled_var = tk.BooleanVar(value=False)
            self.chk_audio = tk.Checkbutton(options_frame, text="Habilitar audio del sistema (WASAPI Loopback)", 
                                           variable=self.audio_enabled_var, bg="#2d2d2d", fg="#ffffff",
                                           selectcolor="#1a1a2e", activebackground="#2d2d2d",
                                           activeforeground="#ffffff", font=('Segoe UI', 10))
            self.chk_audio.grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=5)

            # Estado de ffmpeg y pydub
            if not PYDUB_AVAILABLE:
                tk.Label(options_frame, text="⚠️ pydub no instalado - Ejecuta: pip install pydub", 
                        bg="#2d2d2d", fg="#ff9800", font=('Segoe UI', 9)).grid(row=1, column=0, 
                        columnspan=2, sticky=tk.W, pady=5)
            elif not FFMPEG_AVAILABLE:
                tk.Label(options_frame, text="⚠️ ffmpeg no encontrado - El audio NO se multiplexara en TS", 
                        bg="#2d2d2d", fg="#ff9800", font=('Segoe UI', 9)).grid(row=1, column=0, 
                        columnspan=2, sticky=tk.W, pady=5)
                tk.Label(options_frame, text="   Instalacion: winget install ffmpeg O descarga manual", 
                        bg="#2d2d2d", fg="#888888", font=('Segoe UI', 9)).grid(row=2, column=0, 
                        columnspan=2, sticky=tk.W, pady=2)

            # Info
            info_text = f"""Notas importantes:
- El audio se captura del dispositivo de salida seleccionado usando WASAPI loopback
- Windows 10/11 soporta esta funcion nativamente sin necesidad de Stereo Mix
- Límite máximo de clientes concurrentes: {MAX_CLIENTS}
- Sin audio: usa /stream (MJPEG puro)
- Con audio: usa /stream.ts (MPEG-TS con MP3)
- Para audio MP3 multiplexado se requiere ffmpeg instalado"""

            tk.Label(tab3, text=info_text, bg="#2d2d2d", fg="#888888", 
                    font=('Segoe UI', 9), justify=tk.LEFT, wraplength=700).pack(pady=10, padx=10)

        # ===== FOOTER =====
        footer = tk.Frame(self.root, bg="#1a1a2e", height=30)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        footer.pack_propagate(False)
        tk.Label(footer, text="Python Screen Task 2026 | Basado en ScreenTask de Eslam Hamouda y Ahmad Omar", 
                bg="#1a1a2e", fg="#888888", font=('Segoe UI', 8)).pack(pady=5)

        # Eventos
        self.ip_combo.bind("<<ComboboxSelected>>", lambda e: self.update_url())
        self.port_entry.bind("<KeyRelease>", lambda e: self.update_url())

    def refresh_audio_devices(self):
        """Refresca la lista de dispositivos de audio"""
        audio_devices = self.server.get_audio_devices()
        device_names = []
        for d in audio_devices:
            default_marker = " (PREDETERMINADO)" if d.get('is_default', False) else ""
            device_names.append(f"{d['index']}: {d['name']}{default_marker}")
        
        if not device_names:
            device_names = ["No se encontraron dispositivos WASAPI"]
        
        self.audio_device_combo['values'] = device_names
        if audio_devices:
            # Seleccionar dispositivo predeterminado si existe
            default_idx = 0
            for i, d in enumerate(audio_devices):
                if d.get('is_default', False):
                    default_idx = i
                    break
            self.audio_device_combo.current(default_idx)
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
        """Obtiene el indice del dispositivo de audio seleccionado"""
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

            # Audio solo en modo VLC
            audio_enabled = False
            audio_device_index = None
            if vlc_mode and hasattr(self, 'audio_enabled_var') and self.audio_enabled_var.get():
                audio_enabled = True
                audio_device_index = self.get_audio_device_index()

                if audio_enabled:
                    if not PYDUB_AVAILABLE:
                        self.log("[!] ADVERTENCIA: pydub no instalado - El audio no se convertira a MP3")
                        self.log("    Ejecuta: pip install pydub")
                    elif not FFMPEG_AVAILABLE:
                        self.log("[!] ADVERTENCIA: ffmpeg no encontrado - El audio no se multiplexara en TS")
                        self.log("    Instala ffmpeg: winget install ffmpeg")
                    else:
                        self.log("[+] FFmpeg encontrado - Stream MPEG-TS con audio MP3 disponible")

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

                if audio_enabled and vlc_mode:
                    self.log("[+] Audio del sistema activado (WASAPI Loopback)")
                    if hasattr(self, 'audio_device_combo'):
                        self.log(f"    Dispositivo: {self.audio_device_combo.get()}")
                    if FFMPEG_AVAILABLE and PYDUB_AVAILABLE:
                        self.log(f"    Stream TS: http://{self.server.local_ip}:{port}/stream.ts")
                        self.log("    Formato: MPEG-TS con MJPEG + MP3")
                    else:
                        self.log("    Stream: Solo video (ffmpeg no disponible)")

                if vlc_mode:
                    self.log("=" * 50)
                    self.log("MODO VLC ACTIVADO")
                    self.log("=" * 50)

                    # Determinar URL y mensaje según configuración de audio
                    if audio_enabled and FFMPEG_AVAILABLE and PYDUB_AVAILABLE:
                        vlc_url = f"http://{self.server.local_ip}:{port}/stream.ts"
                        msg = f"Servidor VLC activo con audio.\n\nURL: {vlc_url}\n\nAbrir en VLC: Medio > Abrir flujo de red"
                        msg += "\n\n✅ Audio MP3 incluido en MPEG-TS"
                    elif audio_enabled:
                        vlc_url = f"http://{self.server.local_ip}:{port}/stream"
                        msg = f"Servidor VLC activo (audio sin multiplexar).\n\nURL: {vlc_url}\n\nAbrir en VLC: Medio > Abrir flujo de red"
                        msg += "\n\n⚠️ Audio habilitado pero sin multiplexado TS (instala ffmpeg)"
                    else:
                        vlc_url = f"http://{self.server.local_ip}:{port}/stream"
                        msg = f"Servidor VLC activo (solo video).\n\nURL: {vlc_url}\n\nAbrir en VLC: Medio > Abrir flujo de red"
                        msg += "\n\n🔇 Sin audio"
                    
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