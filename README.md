# automation-engine

Motor de ejecucion de recetas (workflows en YAML) sobre ejecutores intercambiables: navegador real, proxy inteligente o requests HTTP directos.

## Instalacion

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Para el ejecutor `camoufox` hace falta ademas el binario del navegador (no se instala en desarrollo normal):

```
playwright install firefox
camoufox fetch
```

## Uso

```
engine listar
engine validar ejemplo
engine ejecutar ejemplo --data '{"ruta": ""}'
```

`ejecutar` escribe el resultado en `resultados/<receta>_<timestamp>.json`, agrega una linea a `logs/engine.jsonl` y devuelve el JSON del resultado por stdout. Sale con codigo distinto de cero si la receta falla tras agotar los reintentos.

Solo aplica al motor `camoufox` (los otros dos no abren navegador). Por defecto corre sin ventana (`headless: true`). Para verla, dos formas:

```yaml
# en el YAML de la receta, queda fijo para todas las corridas
headless: false
```

```
# o solo para esta corrida, sin tocar el archivo
engine ejecutar mi-receta --no-headless
```

El cursor del motor `camoufox` se mueve con una curva humana por defecto, no salta directo al punto.

### Correr con muchos datos a la vez

```
engine ejecutar mi-receta --data-csv cedulas.csv
```

Corre la receta una vez por fila del CSV. Cada columna se mapea a `{{data.<columna>}}` por nombre: si al grabar marcaste una variable `cedula`, la columna del CSV se llama `cedula`. Cada fila deja su propio resultado en `resultados/` y su propia linea en el log.

```
engine ejecutar mi-receta --data-interactivo
```

En vez de armar el JSON de `--data` a mano, el comando detecta que variables pide la receta y te las pregunta una por una en la terminal.

## Grabar una receta

```
engine grabar https://example.com/login --nombre mi-receta --motor camoufox
```

Se abre una ventana de navegador. Interactuas con el sitio como usuario normal (clics, campos, navegacion) y al cerrar la ventana la grabacion termina. El comando traduce lo grabado a una receta YAML y la deja en `recetas/mi-receta.yaml`. Si `--motor` no se pasa, usa `camoufox`.

Requiere el binario de Chromium de Playwright, una sola vez:

```
playwright install chromium
```

(Se probó usar tu Chrome del sistema via `--channel chrome` para ahorrarse esta descarga, pero el proceso se quedaba colgado despues de cerrar la ventana, de forma reproducible. Se volvio al Chromium gestionado por Playwright.)

Esto es independiente del binario de Camoufox, que solo hace falta para ejecutar recetas con `motor: camoufox`.

### Marcar que extraer: doble clic

Mientras grabas, un clic normal se graba como accion (`clic`). Un **doble clic** en cambio marca ese elemento como algo que quieres extraer: no hace falta copiar ningun selector a mano, ni contestar preguntas despues, el doble clic ya deja el paso `extraer` listo con el selector correcto. Util cuando necesitas varios datos de una vez: cada doble clic agrega uno.

Si despues de cerrar el navegador quieres agregar otro (por ejemplo algo que se te olvido marcar), el comando pregunta igual al final; ahi si pega lo que copiaste del Playwright Inspector (pasando el mouse sobre el dato) y lo traduce solo.

### Variables de los campos rellenados

No pregunta uno por uno. El nombre de la variable sale solo del campo (por ejemplo el campo de `name="Password"` queda como `{{data.password}}`). Si el nombre que puso no te gusta, lo cambias directo en el YAML despues de grabar.

### Lo que no se puede traducir solo

Un `.hover()`, un `.check()`, un drag and drop, etc. no se descarta ni se adivina: el comando pregunta en la terminal que debe pasar ahi, con el codigo grabado a la vista.

### Verificacion antes de guardar

Si `--motor` es `camoufox`, antes de guardar abre el navegador una vez mas (sin ventana) y corre la receta completa para confirmar que cada selector encuentra algo de verdad. Esto agarra errores de tipeo antes de guardarlos, no despues al ejecutar. Si algo no encuentra su elemento, te dice cual paso parece ser y te deja corregir el selector ahi mismo.

## Agregar una receta

Crea un YAML en `recetas/`. Schema:

```yaml
nombre: mi-receta
motor: httpx          # camoufox | trawl | httpx
descripcion: que hace esta receta
headless: true         # opcional, solo aplica a camoufox, default true
pasos:
  - accion: navegar
    url: "https://example.com/{{data.ruta}}"
  - accion: clic
    selector: "#boton"
  - accion: rellenar
    selector: "#campo"
    valor: "{{data.valor}}"
  - accion: extraer
    selector: titulo
    patron: "<title>(.*?)</title>"
  - accion: esperar
    segundos: 2
  - accion: ejecutar_js
    script: "document.title"
```

`{{data.campo}}` se resuelve contra el dict que pasas con `--data` o `--data-file` antes de correr cada paso.

## Agregar un ejecutor

Un archivo nuevo en `src/ejecutores/` que implemente `EjecutorBase.ejecutar(self, receta, datos) -> Resultado`, mas una linea en el registro `EJECUTORES` de `src/ejecutores/__init__.py`. El motor (`src/engine.py`) nunca importa una clase concreta, siempre resuelve por `EJECUTORES[receta.motor]`.

## Configuracion

Variables de entorno (ver `config/.env.example`): `TRAWL_URL`, `TIMEOUT_DEFAULT`, `LOG_LEVEL`.

`TRAWL_URL` es la URL base de una instancia de [Trawl](https://github.com/germondai/trawl) corriendo (self-hosted, via Docker), no un proxy generico: el motor le hace POST a `{TRAWL_URL}/scrape` con la URL objetivo, y Trawl devuelve el HTML ya resuelto (pasa por JS challenges y captchas si hace falta). Sin esta variable, `motor: trawl` falla con `"TRAWL_URL no configurado"`.
