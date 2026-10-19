# Spec — Fork de `remote-desktop-mcp` con clipboard y RDP shared drive

## Repositorio a forkear

**Repositorio original:** `WangYihang/remote-desktop-mcp`  
**URL:** https://github.com/WangYihang/remote-desktop-mcp

El fork debe partir del repositorio anterior y mantener compatibilidad con su forma actual de ejecución mediante `uvx`.


## Restricciones de implementación

- **Mantener el diff mínimo respecto a upstream.** No reestructurar módulos, no sustituir dependencias existentes y no refactorizar código que no sea estrictamente necesario para implementar las nuevas capacidades descritas en esta especificación.
- **Mantener compatibilidad con upstream.** La ejecución mediante `uvx remote-desktop-mcp ...` y el comportamiento de los backends existentes deben continuar funcionando sin cambios para los usuarios actuales.
- No migrar el proyecto a Rust ni reescribir componentes ya funcionales.
- No ampliar el alcance con mejoras arquitectónicas, limpieza general, cambios de estilo o sustitución de librerías salvo que sean imprescindibles para la feature.
- Preferir cambios localizados y fácilmente rebasables sobre futuras versiones de `WangYihang/remote-desktop-mcp`.


---

## 1. Objetivo

Crear un fork de `WangYihang/remote-desktop-mcp` que amplíe el backend RDP existente para permitir:

1. Leer el clipboard remoto de Windows desde MCP.
2. Escribir en el clipboard remoto de Windows desde MCP.
3. Exponer una carpeta local Linux dentro de la sesión Windows mediante RDP drive redirection.
4. Mantener compatibilidad con el comportamiento y CLI actuales.
5. No requerir instalar ningún software adicional en la máquina Windows.

El resultado debe seguir pudiendo ejecutarse con `uvx`.

---

## 2. Caso de uso principal

```text
Linux
├── Claude Code / agente MCP
├── remote-desktop-mcp fork
├── carpeta compartida local
│   └── ~/rdp-share
└── REA / herramientas de análisis

           RDP

Windows remoto
└── aplicación objetivo
```

El agente debe poder:

1. conectarse por RDP;
2. manejar la aplicación;
3. realizar screenshots;
4. leer/copiar texto mediante clipboard;
5. enviar texto mediante clipboard;
6. copiar artefactos Windows a una carpeta Linux compartida;
7. analizar posteriormente esos artefactos localmente.

No debe ser necesario instalar Python, REA, MCP, SSH, agentes ni servicios adicionales en Windows.

---

## 3. Alcance

### 3.1 Clipboard

Añadir soporte MCP explícito para:

```text
clipboard_read
clipboard_write
```

El clipboard debe aprovechar el canal RDP que FreeRDP ya mantiene mediante:

```text
+clipboard
```

No debe implementarse un protocolo de clipboard propio.

### 3.2 Shared drive

Añadir soporte opcional de RDP drive redirection utilizando FreeRDP:

```text
/drive:<name>,<local-path>
```

Ejemplo:

```text
/drive:shared,/home/user/rdp-share
```

Windows deberá poder acceder a la carpeta como recurso RDP, típicamente:

```text
\\tsclient\shared
```

La carpeta pertenece físicamente a Linux.

---

## 4. No objetivos

No implementar en esta fase:

- transferencia mediante protocolo propio;
- servidor SMB;
- SFTP;
- SSH en Windows;
- instalación de agentes Windows;
- ejecución remota de PowerShell fuera de la GUI RDP;
- lectura de memoria de procesos;
- instrumentación dinámica;
- hooks;
- clipboard histórico;
- sincronización automática de directorios;
- múltiples shared drives simultáneos.

Debe mantenerse una implementación pequeña apoyada en las capacidades nativas de FreeRDP.

---

## 5. Compatibilidad

El comportamiento actual debe continuar funcionando sin configuración adicional.

Esto debe seguir siendo válido:

```bash
uvx remote-desktop-mcp mcp rdp
```

con:

```text
REMOTE_DESKTOP_RDP_HOST
REMOTE_DESKTOP_RDP_USER
REMOTE_DESKTOP_RDP_PASSWORD
```

Las nuevas funcionalidades serán opt-in cuando corresponda.

---

## 6. Configuración

### 6.1 Shared directory

Añadir:

```text
REMOTE_DESKTOP_RDP_SHARED_DIR
```

Ejemplo:

```bash
export REMOTE_DESKTOP_RDP_SHARED_DIR="$HOME/rdp-share"
```

Si existe, FreeRDP añadirá:

```text
/drive:shared,<absolute-path>
```

Si no existe, no debe añadirse ninguna redirección de disco.

### 6.2 Shared drive name

Añadir opcionalmente:

```text
REMOTE_DESKTOP_RDP_SHARED_NAME
```

Default:

```text
shared
```

Ejemplo:

```bash
REMOTE_DESKTOP_RDP_SHARED_NAME=rea
```

produce:

```text
/drive:rea,/home/user/rdp-share
```

---

## 7. CLI

Extender:

```bash
remote-desktop-mcp mcp rdp
```

con:

```text
--shared-dir PATH
--shared-name NAME
```

Mapeo:

```text
--shared-dir
REMOTE_DESKTOP_RDP_SHARED_DIR

--shared-name
REMOTE_DESKTOP_RDP_SHARED_NAME
```

Precedencia:

```text
CLI > environment > default
```

Ejemplo:

```bash
uvx remote-desktop-mcp mcp rdp \
  --shared-dir ~/rdp-share \
  --shared-name reverse
```

---

## 8. RDPSession

Modificar:

```text
remote_desktop_mcp/protocol/rdp.py
```

Constructor objetivo:

```python
RDPSession(
    host: str,
    user: str,
    password: str,
    display_num: str = ":99",
    resolution: str = "1280x720",
    shared_dir: str | None = None,
    shared_name: str = "shared",
)
```

---

## 9. Construcción del comando FreeRDP

Mantener los argumentos actuales.

Cuando:

```text
shared_dir != None
```

añadir:

```text
/drive:<shared_name>,<resolved-shared-dir>
```

Ejemplo conceptual:

```text
xfreerdp
/v:host
/u:user
/p:password
/size:1280x720
+clipboard
/drive:shared,/home/user/rdp-share
...
```

---

## 10. Validación de `shared_dir`

Antes de lanzar FreeRDP:

1. expandir `~`;
2. convertir a ruta absoluta;
3. resolver la ruta;
4. comprobar que existe;
5. comprobar que es un directorio.

No crear automáticamente la carpeta.

Si es inválida, fallar con un mensaje claro, por ejemplo:

```text
RDP shared directory does not exist:
/home/user/foo
```

---

## 11. Seguridad del shared drive

No compartir nunca automáticamente `/`, `$HOME`, `cwd` o `/tmp`.

No inferir una carpeta compartida. La redirección solo se habilita cuando `shared_dir` ha sido proporcionado explícitamente.

---

## 12. Clipboard architecture

FreeRDP ya proporciona sincronización mediante:

```text
+clipboard
```

El fork debe interactuar con el clipboard X11 asociado al display de Xvfb.

```text
MCP tool
   ↓
Linux X11 clipboard (:99)
   ↓
FreeRDP clipboard channel
   ↓
Windows clipboard
```

Y al contrario:

```text
Windows clipboard
   ↓
FreeRDP clipboard channel
   ↓
Linux X11 clipboard
   ↓
MCP tool
```

---

## 13. Dependencia de clipboard

Preferir una herramienta pequeña del sistema compatible con X11, como `xclip` o `xsel`.

No añadir una dependencia Python compleja si no es necesaria.

Crear una abstracción interna para no acoplar el servidor MCP directamente al comando externo:

```python
class ClipboardBackend:
    def read_text(self) -> str: ...
    def write_text(self, text: str) -> None: ...
```

---

## 14. Soporte clipboard en `RDPSession`

Añadir:

```python
def read_clipboard(self) -> str
```

y:

```python
def write_clipboard(self, text: str) -> None
```

Solo deben estar disponibles en sesiones de escritorio que soporten clipboard.

En `RDPSession` debe establecerse el display X11 correcto antes de acceder al clipboard:

```text
DISPLAY=:99
```

---

## 15. Herramientas MCP

### `clipboard_read`

```python
clipboard_read() -> str
```

Descripción:

```text
Read text from the clipboard of the active remote desktop session.
```

Si no existe texto, devolver `""`.

### `clipboard_write`

```python
clipboard_write(text: str) -> str
```

Descripción:

```text
Write text to the clipboard of the active remote desktop session.
```

Resultado:

```text
Clipboard updated.
```

No devolver el texto completo cuando sea innecesario.

---

## 16. Semántica de clipboard

`clipboard_write` no debe simular `Ctrl+V`; solo cambia el clipboard.

El agente podrá hacer posteriormente:

```text
clipboard_write(...)
press_hotkey("ctrl+v")
```

---

## 17. Clipboard y secretos

No registrar el contenido del clipboard en logs normales.

Especialmente para passwords, tokens, API keys o datos personales.

Permitido:

```text
clipboard_read
→ log: clipboard_read length=312
```

No permitido:

```text
clipboard_read value="secret..."
```

Lo mismo para `clipboard_write`.

---

## 18. Trace

El trace podrá registrar:

```json
{
  "action": "clipboard_read",
  "length": 123
}
```

```json
{
  "action": "clipboard_write",
  "length": 456
}
```

Nunca registrar el contenido por defecto.

---

## 19. Capacidad MCP adicional recomendada

Añadir:

```text
shared_drive_info
```

Firma:

```python
shared_drive_info() -> dict
```

Resultado conceptual:

```json
{
  "enabled": true,
  "name": "shared",
  "local_path": "/home/user/rdp-share",
  "windows_path": "\\\\tsclient\\shared"
}
```

Si no está configurado:

```json
{
  "enabled": false
}
```

---

## 20. No implementar `file_read` / `file_write` remotos

No añadir todavía herramientas MCP como:

```text
download_remote_file
upload_remote_file
read_windows_file
write_windows_file
```

La transferencia debe hacerse mediante la GUI Windows y:

```text
\\tsclient\<shared-name>
```

Esto evita crear un segundo sistema de acceso remoto.

---

## 21. Workflow esperado

Para texto:

```text
Claude:
take_screenshot()

Claude:
mouse_click(...)

Claude:
press_hotkey("ctrl+c")

Claude:
clipboard_read()
```

Para transferir un binario:

```text
C:\Program Files\Target\app.exe
→ Copy
\\tsclient\shared
→ Paste
```

Linux obtiene:

```text
~/rdp-share/app.exe
```

REA puede analizar después ese artefacto local.

---

## 22. Interfaces base

Si encaja con la arquitectura actual, extender `DesktopSession` con capacidades opcionales:

```python
supports_clipboard: bool
```

```python
read_clipboard()
write_clipboard()
```

No forzar implementaciones ficticias en VNC, ADB, Playwright o Local si no tienen soporte equivalente.

Preferir detección de capabilities frente a métodos que fallen silenciosamente.

---

## 23. Errores

Mensajes claros y accionables:

```text
Clipboard is not supported by the active session.
Clipboard backend 'xclip' is unavailable.
RDP shared directory does not exist.
No active desktop session.
```

No producir traceback al usuario MCP para errores esperados.

---

## 24. Startup check

Al iniciar una sesión RDP, comprobar que existe el backend de clipboard requerido, por ejemplo `xclip`.

Si no existe:

- la sesión RDP podrá continuar;
- clipboard MCP se marcará como no disponible;
- no abortar toda la conexión salvo que clipboard haya sido explícitamente requerido.

---

## 25. Tests unitarios

### FreeRDP args

Sin shared dir: no debe aparecer `/drive:`.

Con:

```text
shared_dir=/tmp/share
shared_name=rea
```

esperar:

```text
/drive:rea,/tmp/share
```

### Path normalization

`~/foo` debe resolverse correctamente.

### Invalid paths

- fichero en lugar de directorio → error;
- path inexistente → error.

### Clipboard tools

Mock de `read_clipboard` y `write_clipboard` y tests de `clipboard_read` / `clipboard_write`.

### Logging

Confirmar que el contenido del clipboard no aparece en logs o trace.

---

## 26. Integration tests

### Clipboard Linux → Windows

```text
clipboard_write("remote-mcp-test")
```

Dentro de Windows, `Ctrl+V` debe producir:

```text
remote-mcp-test
```

### Clipboard Windows → Linux

Copiar en Windows:

```text
windows-test
```

Después:

```text
clipboard_read()
```

debe devolver `windows-test`.

### Shared drive

Crear localmente:

```text
/tmp/rdp-share/test.txt
```

Windows debe visualizar:

```text
\\tsclient\shared\test.txt
```

### Windows → Linux

Desde Windows copiar un fichero a:

```text
\\tsclient\shared
```

Debe aparecer en `/tmp/rdp-share` con contenido idéntico.

---

## 27. Compatibilidad regresiva

No pueden romperse las capacidades actuales:

```text
take_screenshot
tap
mouse_click
mouse_move
mouse_scroll
type_text
press_key
press_hotkey
recording
trace
```

La conexión RDP existente debe continuar funcionando sin configurar ninguna nueva variable.

---

## 28. Documentación

Actualizar README con una sección:

```text
RDP clipboard and shared directory
```

Ejemplo mínimo:

```bash
export REMOTE_DESKTOP_RDP_SHARED_DIR="$HOME/rdp-share"
export REMOTE_DESKTOP_RDP_SHARED_NAME="shared"

uvx remote-desktop-mcp mcp rdp
```

Explicar la ruta Windows:

```text
\\tsclient\shared
```

---

## 29. Ejemplo configuración MCP

```json
{
  "mcpServers": {
    "remote-desktop": {
      "command": "uvx",
      "args": [
        "remote-desktop-mcp",
        "mcp",
        "rdp"
      ],
      "env": {
        "REMOTE_DESKTOP_RDP_HOST": "host:port",
        "REMOTE_DESKTOP_RDP_USER": "user",
        "REMOTE_DESKTOP_RDP_PASSWORD": "...",
        "REMOTE_DESKTOP_RDP_SHARED_DIR": "/home/user/rdp-share",
        "REMOTE_DESKTOP_RDP_SHARED_NAME": "shared"
      }
    }
  }
}
```

Las credenciales no deben almacenarse en el repositorio.

---

## 30. Estructura de cambios esperada

Principalmente:

```text
remote_desktop_mcp/
├── protocol/
│   ├── base.py
│   └── rdp.py
│
└── mcp/
    ├── __main__.py
    └── server.py
```

Opcional:

```text
remote_desktop_mcp/
└── clipboard/
    ├── __init__.py
    └── x11.py
```

si separar el backend mejora la arquitectura.

---

## 31. Prioridad de implementación

### P0

```text
shared-dir
FreeRDP /drive
```

Es la funcionalidad más importante para mover artefactos Windows → Linux.

### P1

```text
clipboard_read
clipboard_write
```

### P2

```text
shared_drive_info
logging seguro
tests integración
```

---

## 32. Definition of Done

La feature se considera terminada cuando desde un agente MCP ejecutándose en Linux se puede:

1. conectar a Windows por RDP;
2. tomar screenshots;
3. interactuar con la GUI;
4. copiar texto en Windows y leerlo mediante `clipboard_read`;
5. escribir texto mediante `clipboard_write` y pegarlo en Windows;
6. acceder desde Windows a `\\tsclient\shared`;
7. copiar un fichero desde Windows a esa carpeta;
8. encontrar ese fichero inmediatamente en Linux;
9. realizar todo lo anterior sin instalar software adicional en Windows;
10. ejecutar la configuración antigua sin cambios.

---

## 33. Restricción arquitectónica

La implementación debe utilizar las capacidades estándar de RDP/FreeRDP siempre que existan.

No reinventar:

```text
clipboard transport
file transfer
remote filesystem protocols
```

El MCP debe actuar como una capa fina sobre las capacidades existentes.

---

## 34. Futuras extensiones

Fuera de esta feature, pero dejar la arquitectura preparada para:

```text
multiple shared drives
clipboard file transfer
remote file picker helpers
session capability discovery
audio redirection
printer redirection
smartcard redirection
USB redirection
dynamic resolution
multi-monitor
```

No implementarlas ahora.
