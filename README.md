📋 ENTRADAS PARA GITHUB
1. BADGES / SHIELDS (top del README)
markdown
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)
![Version](https://img.shields.io/badge/Version-3.0.0-e94560)
![Status](https://img.shields.io/badge/Status-Stable-success)
2. DESCRIPCIÓN / OBJETIVO
Markdown
Copy
Code
Preview
## 🎯 Objetivo

**Python Screen Task** es una aplicación de escritorio que permite compartir tu pantalla en tiempo real dentro de tu red local, sin necesidad de conexión a Internet. 

Incluye soporte para **streaming de video MJPEG** y **audio del sistema vía WASAPI loopback** multiplexado en formato **MPEG-TS** para reproducción en VLC.

### Características principales
- 🖥️ **Captura de pantalla** multi-monitor con selección de resolución
- 🔊 **Audio del sistema** (WASAPI loopback) sin necesidad de "Stereo Mix"
- 📡 **Modo VLC** con stream MPEG-TS (video + audio MP3)
- 🌐 **Interfaz web** responsive para visualización en navegador
- 🔒 **Modo privado** con autenticación HTTP Basic
- 👥 **Límite de 5 conexiones** simultáneas
- 🏠 **100% local** - sin servicios en la nube
3. CAPTURA DE PANTALLA (opcional)
markdown
## 📸 Vista previa

![Interfaz principal](docs/screenshot_main.png)
*Interfaz gráfica con pestañas de configuración*

![Modo VLC](docs/screenshot_vlc.png)
*Página de instrucciones para VLC*
4. REQUERIMIENTOS / PREREQUISITOS
Markdown
Copy
Code
Preview
## 📦 Requerimientos

### Sistema operativo
| SO | Versión | Arquitectura |
|----|---------|--------------|
| Windows | 10/11 | x64 |

### Dependencias de Python
```txt
pyautogui>=0.9.54
mss>=9.0.1
Pillow>=10.0.0
PyAudioWPatch>=0.2.12.6
pydub>=0.25.1
Software externo obligatorio
Table
Software	Uso	Descarga
FFmpeg	Multiplexación audio/video en MPEG-TS	ffmpeg.org
VLC Media Player	Receptor del stream (modo VLC)	videolan.org
Instalación rápida de FFmpeg
powershell
# Via winget (recomendado)
winget install ffmpeg

# O manual: extraer ffmpeg.exe en C:\ffmpeg\bin\ y agregar al PATH
Requisitos de hardware
RAM: 512 MB mínimo (2 GB recomendado)
Red: Conexión LAN/WiFi en el mismo segmento de red
Audio: Tarjeta de sonido con drivers WASAPI (Windows 10/11 nativo)
plain

---

### 5. PASOS PARA USARLO

```markdown
## 🚀 Pasos para usarlo

### 1. Instalación
```bash
# Clonar repositorio
git clone https://github.com/lgona/ScreenTask.git
cd ScreenTask

# Crear entorno virtual (recomendado)
python -m venv venv
.\venv\Scripts\activate

# Instalar dependencias
pip install -r requirements.txt
2. Ejecutar la aplicación
bash
python deepseek_python_AUDIO_2.py
3. Configurar streaming
Modo Web (solo video)
Selecciona pestaña "Calidad, Monitor y Privacidad"
Ajusta calidad JPEG, FPS y resolución
Click en "INICIAR SERVIDOR"
Abre el navegador en la URL mostrada (ej: http://192.168.1.4:8080)
Modo VLC (video + audio)
Ve a pestaña "Configuración de Audio"
Selecciona tu dispositivo de salida (ej: "Altavoces")
✅ Activa "Habilitar audio del sistema"
Click en "TRANSMITIR A VLC"
Abre VLC → Medio > Abrir flujo de red
Pega la URL:
Con audio: http://192.168.1.4:8080/stream.ts
Sin audio: http://192.168.1.4:8080/stream
4. Compartir en red
La URL funciona para cualquier dispositivo en tu misma red
Máximo 5 clientes simultáneos
Para acceso privado: activa "Tarea Privada" e ingresa usuario/contraseña
⚠️ Solución de problemas comunes
Table
Problema	Solución
Invalid number of channels	Instala PyAudioWPatch (no PyAudio normal): pip install PyAudioWPatch
ffmpeg no encontrado	Instala FFmpeg y agrega al PATH: winget install ffmpeg
404 en /stream.ts	Verifica que el audio esté habilitado y el dispositivo WASAPI esté activo
Pantalla negra en VLC	Usa /stream en lugar de /stream.ts para video puro
Alta latencia	Reduce calidad JPEG (< 50) o aumenta ms_interval (> 100)
plain

---

### 6. VERSIÓN / CHANGELOG

```markdown
## 🏷️ Versión

**Actual: v3.0.0** (2026)

### Historial de versiones

| Versión | Fecha | Cambios |
|---------|-------|---------|
| **v3.0.0** | 2026-06 | Audio WASAPI loopback, MPEG-TS multiplexado, interfaz por pestañas, límite 5 clientes |
| v2.0.0 | 2025 | Soporte multi-monitor, modo VLC, autenticación privada |
| v1.0.0 | 2024 | Port inicial a Python, captura básica MJPEG |

### Basado en
- **ScreenTask Windows** © [Eslam Hamouda](https://github.com/EslaMx7/ScreenTask) (2014)
- **ScreenTask Genérico** © [Ahmad Omar](https://github.com/ahmadomar/ScreenTask) (2014)
