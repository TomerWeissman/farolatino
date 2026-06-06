# Instalación de FaroAI

Una guía breve y sin tecnicismos, desde "abrí tu navegador" hasta "usá la
app". Unos 5 minutos la primera vez. Después, doble clic en el ícono de
FaroAI y se abre.

Si un paso no funciona, andá a **Solución de problemas** al final.

---

## Lo que vas a necesitar

- Una computadora con Mac o Windows.
- Conexión a internet.
- Las credenciales que te pasó Tomer (en tu correo de bienvenida o en el
  archivo `faroai-team-keys.txt`):
  - Una **clave del Modelo de IA** (empieza con `sk-ant-`, `sk-` o `AIza`).
  - Un **refresh token de Chartmetric** (una cadena larga al azar).
  - Los **5 códigos de Power BI** (las líneas que empiezan con `PBI_`).

Tené todo a mano — lo vas a pegar dentro de la app en el primer arranque.

---

## Instalación en Mac

### Paso 1 — Descargar FaroAI

1. Abrí tu navegador.
2. Andá a: **<https://github.com/farolatino-app/farolatino/releases/latest>**
3. Bajá hasta la sección **Assets**.
4. Hacé clic en el archivo que termina en **`.dmg`** (algo como
   `FaroAI-v0.5.91.dmg` — el número de versión cambia con el tiempo).
   Pesa ~84 MB.

El archivo queda en tu carpeta **Descargas**.

### Paso 2 — Instalar la app

1. Doble clic en el `.dmg`. Aparece una ventana con un ícono de `FaroAI`.
2. Arrastrá ese ícono de `FaroAI` a tu carpeta **Aplicaciones**.
3. Expulsá la imagen de disco: en la barra lateral del Finder, hacé clic
   en el ⏏ al lado de `FaroAI`.

### Paso 3 — Desbloquear la app (una sola vez, ~30 segundos)

Como FaroAI no está firmada por una cuenta de Apple Developer, macOS se va
a negar a abrirla la primera vez. La desbloqueamos con un comando de
Terminal. Solo lo hacés una vez por computadora.

1. Apretá **Cmd + Espacio** para abrir Spotlight.
2. Escribí **Terminal** y Enter. Se abre una ventanita de texto.
3. Hacé clic en la ventana de Terminal y **copiá y pegá esta línea exacta**
   (no la tipees a mano — copiala de acá):

   ```
   xattr -cr /Applications/FaroAI.app 2>/dev/null; open /Applications/FaroAI.app
   ```

4. Apretá Enter.
5. FaroAI se abre y aparece la pantalla de bienvenida.

> Si tu Mac muestra un cartel que dice *"FaroAI está dañada y no se puede
> abrir"* antes de correr el comando, **hacé clic en Cancelar — nunca en
> "Mover a la Papelera"**, o se borra la app y vas a tener que descargarla
> de nuevo. Cancelar la deja en su lugar; el comando de arriba la desbloquea.

### Paso 4 — Pegá tus credenciales

La pantalla de bienvenida tiene varias secciones:

1. **Modelo de IA** (obligatorio) — pegá la clave `sk-ant-…` / `sk-…` /
   `AIza…`. La app detecta sola de qué proveedor es. *Es el único campo
   obligatorio para poder entrar.*
2. **Chartmetric** — pegá el refresh token.
3. **Power BI** — pegá las **5 líneas `PBI_`** del archivo de claves del
   equipo en el recuadro. Acepta tanto `CLAVE=valor` como `CLAVE: valor`.
4. (Opcional) **Spotify** y **YouTube**, si los tenés.

Hacé clic en **Empezar**. Listo.

### Próximos arranques

Doble clic en el ícono de FaroAI en Aplicaciones. No hace falta Terminal —
el desbloqueo del Paso 3 es permanente.

---

## Instalación en Windows

### Paso 1 — Descargar FaroAI

1. Abrí tu navegador.
2. Andá a: **<https://github.com/farolatino-app/farolatino/releases/latest>**
3. Bajá hasta la sección **Assets**.
4. Hacé clic en el archivo que empieza con **`FaroAI-Setup-`** y termina en
   **`.exe`** (ej. `FaroAI-Setup-v0.5.91.exe`). ~29 MB.

### Paso 2 — Ejecutar el instalador

1. Encontrá el archivo en Descargas y hacé doble clic.
2. Windows muestra un cartel azul **"Windows protegió tu PC"**. Es normal —
   es precaución con una app que todavía no conoce. Hacé clic en el enlace
   **Más información** arriba.
3. Aparece un botón **Ejecutar de todos modos** abajo. Clic.
4. Seguí el asistente: **Siguiente** → **Instalar** → **Finalizar**.

Queda un ícono **FaroAI** en el Escritorio y en el menú Inicio.

### Paso 3 — Abrir y pegar credenciales

1. **Doble clic en el ícono de FaroAI** del Escritorio. (O Inicio → escribí
   FaroAI → Enter.)
2. En la pantalla de bienvenida pegá:
   - **Modelo de IA** (obligatorio): la clave `sk-ant-…` / `sk-…` / `AIza…`.
   - **Chartmetric**: el refresh token.
   - **Power BI**: las 5 líneas `PBI_`.
   - (Opcional) Spotify y YouTube.
3. Hacé clic en **Empezar**.

### Próximos arranques

Doble clic en el ícono de FaroAI del Escritorio. Eso es todo.

---

## Actualizaciones

Cuando Tomer publica una versión nueva, FaroAI se actualiza sola — sin
volver a descargar instaladores.

1. Abrí FaroAI.
2. Hacé clic en **Connections** (Conexiones) en la barra lateral.
3. Bajá hasta la sección **Updates** y hacé clic en **Check for updates**
   (Buscar actualizaciones).
4. Si hay una versión nueva, hacé clic en **Apply** (Aplicar). Descarga los
   cambios (~1–5 MB), se reinicia y quedás en la versión nueva.

---

## Idioma

FaroAI viene **en español por defecto**. Para cambiar a inglés:
**Settings** (Ajustes) → **Idioma** → **English**. Tu elección se guarda
entre sesiones.

---

## Solución de problemas

| Lo que ves | Qué hacer |
|---|---|
| Mac: "FaroAI no se puede abrir" o el ícono desapareció de Aplicaciones | Te salteaste el Paso 3 (el comando de Terminal), o tocaste "Mover a la Papelera" por error. Volvé a descargar el `.dmg`, arrastrá FaroAI a Aplicaciones y corré el comando del Paso 3 **antes** de abrir la app. |
| Windows: SmartScreen no muestra "Ejecutar de todos modos" | Algunas PCs de trabajo lo deshabilitan por política. Pedile a IT que permita el instalador, o usá una máquina personal. |
| "Clave de Modelo de IA no detectada" | La clave tiene que ir exacta — sin comillas ni espacios al principio o al final. Pegala directo desde el correo. |
| Power BI en rojo / los datos internos no aparecen | Revisá que hayas pegado las **5** líneas `PBI_` completas en el recuadro de Power BI. |
| La página de Connections muestra Chartmetric en rojo | El token está mal o expiró. Volvé a pegarlo; si sigue en rojo, pedile uno nuevo a Tomer. |

¿Seguís trabado? Mandale un mensaje a Tomer con una captura de la pantalla
donde estás — casi siempre alcanza para resolverlo a distancia.

- **Captura en Mac**: `Cmd + Shift + 4`, arrastrá un recuadro. Se guarda en
  el Escritorio.
- **Captura en Windows**: `Win + Shift + S` para seleccionar un recuadro,
  después pegala en un chat o correo.

---

Bienvenido/a a FaroAI.
