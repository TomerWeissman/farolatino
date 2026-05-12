# Instalación de FaroAI — Paso a Paso

Una guía sin tecnicismos, desde "abre tu navegador web" hasta "usa la
aplicación". Aproximadamente 15–20 minutos la primera vez. Después,
doble clic en un ícono y listo.

Si un paso no funciona, salta a **Solución de problemas** al final.

---

## Lo que necesitas antes de empezar

- Una computadora con macOS o Windows.
- Conexión a internet.
- Una **cuenta de Anthropic** — gratuita; la creas en el Paso 4 si
  todavía no la tienes. No requiere tarjeta de crédito.
- Un **refresh token de Chartmetric** — ya lo tienes. Tenlo a la mano
  en una nota; lo pegarás en el último paso.

Eso es todo. Sin suscripciones de pago, sin herramientas de
desarrollador.

---

## Paso 1 — Descargar FaroAI desde GitHub

1. Abre tu navegador web (Safari, Chrome, Edge — cualquiera funciona).
2. Ve a: **<https://github.com/TomerWeissman/farolatino/releases/latest>**
3. La página tendrá un número de versión en el título, por ejemplo
   "v0.1.0". Desplázate hacia abajo hasta la sección **Assets**.
4. Haz clic en **`farolatino-v0.1.0.zip`** para descargarlo.
5. Encuentra el archivo en tu carpeta **Descargas**.
   - **Mac**: abre Finder -> Descargas (Downloads).
   - **Windows**: abre el Explorador de archivos -> Descargas.
6. Haz doble clic en el `.zip` para descomprimirlo. Obtendrás una
   carpeta llamada `farolatino-v0.1.0`.
7. Mueve esa carpeta a un lugar donde puedas encontrarla — tu carpeta
   **Documentos** es una buena opción.

> Si la página de Releases no muestra un archivo `.zip`, escríbele a
> Tomer — puede que aún no se haya publicado una versión.

---

## Paso 2 — Instalar Python

Python es el lenguaje en el que corre FaroAI. Lo instalas una vez y te
olvidas de que existe.

1. Ve a **<https://www.python.org/downloads/>**
2. Haz clic en el botón amarillo grande **Download Python 3.x**
   (cualquier versión 3.11 o superior funciona).
3. Abre el instalador descargado.

### En Mac

- Haz doble clic en el instalador y haz clic en **Continuar** en cada
  pantalla, luego en **Instalar**.

### En Windows

- **IMPORTANTE**: en la primera pantalla del instalador, marca la
  casilla **Add Python to PATH** antes de hacer clic en Install. Si te
  olvidas, ejecuta el instalador otra vez y márcala.

### Verificar que funcionó

Necesitas abrir Terminal (Mac) o PowerShell (Windows). Si nunca lo has
hecho:

- **Mac**: presiona `Cmd + Espacio`, escribe `Terminal` y presiona
  Enter. Aparece una pequeña ventana negra.
- **Windows**: presiona la tecla Windows, escribe `PowerShell` y
  presiona Enter. Aparece una ventana azul.

En esa ventana, escribe esto exactamente y presiona Enter:

```
python3 --version
```

(En Windows, escribe `python --version`.)

Deberías ver algo como `Python 3.11.5`. Si obtienes "command not
found":

- **Mac**: cierra Terminal, vuélvela a abrir y prueba de nuevo.
- **Windows**: vuelve a ejecutar el instalador de Python y marca **Add
  Python to PATH**.

Puedes cerrar la ventana de Terminal/PowerShell después de esta
verificación.

---

## Paso 3 — Instalar Node.js

FaroAI usa Claude Code como motor de IA, y Claude Code requiere
Node.js. Mismo procedimiento — instalar una vez y olvidarlo.

1. Ve a **<https://nodejs.org/>**
2. Haz clic en el botón verde grande **LTS** a la izquierda.
3. Abre el instalador y haz clic en **Continuar** / **Siguiente** en
   cada pantalla — no cambies ningún valor por defecto.

Para verificar, abre Terminal/PowerShell de nuevo (cierra cualquier
ventana antigua primero para que detecte la nueva instalación) y
escribe:

```
node --version
```

Deberías ver `v20.x.x` o algo similar.

---

## Paso 4 — Instalar Claude Code

Claude Code es el motor de IA que FaroAI usa para responder preguntas.

1. Ve a **<https://claude.com/claude-code>**
2. Sigue las instrucciones de instalación en esa página. Generalmente
   es un solo comando que pegas en Terminal/PowerShell.
3. Una vez que termine, en la misma ventana de Terminal/PowerShell,
   escribe:

   ```
   claude login
   ```

4. Tu navegador web se abrirá. Inicia sesión con una **cuenta de
   Anthropic**. Si no tienes una, haz clic en **Sign up** — es gratis,
   sin tarjeta de crédito.
5. Aprueba los permisos que Claude Code solicita.
6. Vuelve a Terminal — debería decir algo como "Logged in".

Esto solo se hace **una vez**. Los lanzamientos futuros de FaroAI no
lo necesitan.

---

## Paso 5 — Iniciar FaroAI

La configuración está lista. Ahora a iniciar la aplicación:

### En Mac

1. Abre Finder y navega hasta la carpeta `farolatino-v0.1.0`.
2. Encuentra el archivo llamado `start.command`.
3. **Haz clic derecho** sobre él y elige **Abrir**. (En un trackpad,
   "clic derecho" es un toque con dos dedos, o mantén presionada la
   tecla `Control` mientras haces clic.)
4. macOS preguntará "¿Estás seguro de que quieres abrirlo?" — haz clic
   en **Abrir**.

> El clic derecho solo es necesario la primera vez. Después puedes
> hacer doble clic normalmente.

### En Windows

1. Abre el Explorador de archivos y navega hasta la carpeta
   `farolatino-v0.1.0`.
2. Encuentra el archivo llamado `start.bat`.
3. **Haz doble clic** sobre él.
4. Windows SmartScreen puede decir "Windows protegió tu equipo" — haz
   clic en **Más información** -> **Ejecutar de todos modos**.

### Lo que sucede después

Se abre una ventana de Terminal y muestra mensajes de progreso. El
primer lanzamiento toma alrededor de **60 segundos** mientras se
configura todo; los siguientes toman ~5 segundos.

Cuando esté listo, tu navegador web se abrirá automáticamente con el
dashboard de FaroAI. **No cierres la ventana de Terminal** — cerrarla
apaga la aplicación. Solo minimízala y olvídate de ella.

---

## Paso 6 — Pega tu token de Chartmetric (en la app)

El dashboard está abierto. Último paso:

1. En la barra lateral izquierda, haz clic en **Connections**
   (Conexiones).
2. Verás filas para Chartmetric, Spotify y YouTube. Haz clic en la
   fila de **Chartmetric** para expandirla.
3. Pega tu refresh token de Chartmetric en el cuadro de texto.
4. Haz clic en **Save** (Guardar). El indicador de estado en esa fila
   debería volverse verde y decir "ok".
5. Haz clic en **FaroAI** en la parte superior de la barra lateral
   para volver al chat.

Listo. Prueba escribiendo **`@evaluate Bad Bunny`** para ver un
dossier completo del artista.

---

## Uso diario

- **Iniciar FaroAI**: doble clic en `start.command` (Mac) o
  `start.bat` (Windows). El navegador se abre solo. Toma ~5 segundos.
- **Detener FaroAI**: cierra la ventana de Terminal. Tu pestaña del
  navegador puede quedarse abierta — solo mostrará un error de
  conexión hasta que la inicies de nuevo.
- **Actualizar FaroAI**: cuando salga una nueva versión, descarga el
  `.zip` nuevo desde GitHub igual que en el Paso 1, descomprímelo y
  reemplaza tu carpeta antigua. Tu token de Chartmetric vive en un
  archivo oculto dentro de la carpeta; la forma más fácil de
  conservarlo es volver a pegarlo en la página de Connections después
  de actualizar.

---

## Solución de problemas

| Lo que ves | Lo que significa | Qué hacer |
|---|---|---|
| Terminal/PowerShell se cierra apenas se abre | Falta algo — generalmente Python o Claude Code | Vuelve a iniciar `start.command` / `start.bat`, observa la ventana para ver el mensaje de error real |
| La ventana dice "Python isn't installed" | El Paso 2 no funcionó | Repite el Paso 2; en Windows asegúrate de marcar **Add Python to PATH** |
| La ventana dice "Claude Code isn't installed" | El Paso 4 no funcionó | Repite los Pasos 3 y 4 |
| `claude: command not found` al ejecutar `claude login` | Node.js o Claude Code no está en tu PATH | Reinicia Terminal/PowerShell y prueba de nuevo. Si sigue fallando, repite los Pasos 3 y 4 |
| El navegador muestra "This site can't be reached" | El lanzador todavía está iniciando | Espera 5 segundos y recarga la pestaña |
| "Address already in use" | Una FaroAI anterior sigue corriendo | Cierra esa ventana de Terminal y reinicia |
| El chat dice "Backend closed the stream..." | La conexión con el lanzador se cayó | Cierra Terminal y reinicia |
| La página de Connections muestra Chartmetric en rojo | El token está mal o expiró | Vuelve a pegarlo; si sigue rojo, el token fue rotado — pídele uno nuevo a Tomer |

¿Sigues atascado? Toma una captura de la ventana de Terminal (el
mensaje de error aparece textualmente ahí) y envíasela a Tomer. Eso
casi siempre alcanza para resolverlo a distancia.

- **Captura en Mac**: `Cmd + Shift + 4`, arrastra un cuadro alrededor
  de la ventana de Terminal. La imagen se guarda en tu Escritorio.
- **Captura en Windows**: presiona `PrtScn` (o `Win + Shift + S` para
  un cuadro de selección), luego pégala en un chat o correo.

---

## Lo que puedes ignorar tranquilamente

- El archivo oculto **`.env`** dentro de la carpeta de FaroAI. La
  página de Connections en la app maneja todo lo que hay adentro por
  ti.
- Las otras subcarpetas (`api`, `core`, `web`, …) — son el código
  fuente de la app. No las muevas ni las renombres.

Bienvenido(a) a FaroAI.
