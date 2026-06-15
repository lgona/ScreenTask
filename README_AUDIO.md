🎧 Configuración de VB-CABLE (una sola vez)
Descarga e instala VB-CABLE desde vb-audio.com/Cable
Ve a Panel de Control → Sonido → Grabación
Habilita "CABLE Output (VB-Audio Virtual Cable)"
Clic derecho → Propiedades → Escuchar
✅ Marca "Escuchar este dispositivo"
Selecciona tus altavoces en "Reproducir a través de"
Con esto, TODO el audio de tu PC se redirige a VB-CABLE y el servidor lo captura como un dispositivo de entrada estándar.
🌐 URLs generadas al iniciar
Table
Recurso	URL
Interfaz Web	http://IP:8080/
Stream Video	http://IP:8080/stream (MJPEG)
Stream Audio	http://IP:5000/audio (WAV PCM)
📺 Uso en VLC (Modo VLC)
Cuando inicias en "Transmitir a VLC", la página muestra:
plain
URL Video:  http://IP:8080/stream
URL Audio:  http://IP:5000/audio
En VLC:
Medio → Abrir flujo de red → pega la URL de video
Audio → Pista de audio → Agregar pista → pega la URL de audio
🖥️ Uso en Navegador (Modo Web)
La interfaz web ahora incluye automáticamente un reproductor de audio HTML5 que se conecta a http://IP:5000/audio. Solo abre la página y escucharás el audio del sistema sincronizado con la pantalla.
✅ Ventajas de esta solución
No requiere ffmpeg ni pydub
No requiere WASAPI loopback (compatible con cualquier Windows)
Audio y video son independientes — si uno falla, el otro sigue
Funciona con VB-CABLE, Stereo Mix, o cualquier dispositivo de entrada
El navegador reproduce audio nativamente sin plugins
Código mucho más simple y estable (sin pipes ni procesos ffmpeg)
