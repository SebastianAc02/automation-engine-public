# Guia operativa: rutas, recetas y Trawl

Referencia rapida de donde esta cada cosa y como correrla. Para como funciona el motor por dentro (acciones, selectores, variables), ver `README.md`.

## Ubicacion del proyecto

```
/Users/sebastianacostamolina/01_Documents/06_onepay/automation-engine/
```

Repo propio en GitHub: `github.com/SebastianAc02/automation-engine` (privado). Hermano de `followups-tool`, ambos dentro de `06_onepay/`.

## Arrancar

```bash
cd /Users/sebastianacostamolina/01_Documents/06_onepay/automation-engine
source .venv/bin/activate
```

## Estructura de archivos (rutas exactas)

```
automation-engine/
├── .env                        # config real (TRAWL_URL, TIMEOUT_DEFAULT, LOG_LEVEL) - no esta en git
├── config/
│   ├── settings.py             # define que variables de entorno existen
│   └── .env.example            # plantilla
├── src/
│   ├── cli.py                  # los 4 comandos: ejecutar, listar, validar, grabar
│   ├── engine.py                # carga la receta YAML, corre los pasos con reintentos
│   ├── models.py                 # Receta, Paso, Resultado (schema de todo)
│   ├── ejecutores/
│   │   ├── base.py               # interfaz comun + coincidencia_texto() (logica de regex compartida)
│   │   ├── camoufox.py           # motor camoufox (navegador real)
│   │   ├── httpx.py              # motor httpx (requests directos)
│   │   └── trawl.py              # motor trawl (habla con el servicio Trawl, ver mas abajo)
│   └── grabador/
│       ├── grabar.py             # lanza playwright codegen
│       ├── parser.py             # traduce el script grabado a pasos
│       └── receta.py             # arma el YAML final, verifica selectores
├── recetas/                    # cada receta es un archivo .yaml aca
├── resultados/                 # un .json por cada corrida de `engine ejecutar`
├── logs/engine.jsonl            # una linea por corrida (receta, motor, exito, duracion)
└── tests/                       # 39 tests, `pytest -q` desde la raiz
```

## Recetas existentes: donde estan y como se corren

Todas viven en `recetas/<nombre>.yaml`. El comando siempre es `engine ejecutar <nombre> --data '{...}'`.

| Receta | Archivo | Motor | Variable(s) que pide | Comando |
|---|---|---|---|---|
| `ejemplo` | `recetas/ejemplo.yaml` | httpx | `ruta` | `engine ejecutar ejemplo --data '{"ruta": ""}'` |
| `dian` | `recetas/dian.yaml` | camoufox | `cedula` | `engine ejecutar dian --data '{"cedula": "TU_CEDULA"}' --no-headless` |
| `einforma` | `recetas/einforma.yaml` | trawl | `slug` | `engine ejecutar einforma --data '{"slug": "nombre-empresa-einforma"}'` |
| `informacolombia` | `recetas/informacolombia.yaml` | trawl | `slug` | `engine ejecutar informacolombia --data '{"slug": "tucable-sas"}'` |
| `portafolio` | `recetas/portafolio.yaml` | trawl | `slug` | `engine ejecutar portafolio --data '{"slug": "NOMBRE-EMPRESA-MAYUSCULAS"}'` |
| `prueba-flujo` | `recetas/prueba-flujo.yaml` | camoufox | ninguna | `engine ejecutar prueba-flujo` |
| `prueba-grabador` | `recetas/prueba-grabador.yaml` | camoufox | ninguna | `engine ejecutar prueba-grabador --no-headless` |

Las tres de `motor: trawl` (`einforma`, `informacolombia`, `portafolio`) sacan el telefono de una empresa, cada una de un directorio distinto, y ya estan probadas contra los servicios reales:
- `einforma` y `informacolombia`: confirmadas, mismo telefono real (`3205582644`, empresa Tucable S A S) sacado de dos directorios distintos.
- `portafolio`: confirmada con otra empresa (`LEGON-COMUNICACIONES-SAS` -> `6063419496`). Ojo: la variable ahi tambien se llama `slug`, pero es el **nombre de la empresa en mayusculas con guiones**, no el NIT (la URL real de Portafolio.co no usa NIT).

`dian` esta confirmada de punta a punta con una cedula real: llega hasta sacar los ultimos 4 digitos del celular al que se manda el codigo de verificacion (el codigo en si nunca aparece en la pagina, se lo mandan por SMS al celular real).

Otras formas de correr cualquiera de estas, en vez de `--data`:
```bash
engine ejecutar <receta> --data-interactivo        # pregunta cada variable en la terminal
engine ejecutar <receta> --data-csv archivo.csv    # una corrida por fila del csv
engine ejecutar <receta> --no-headless             # solo aplica a camoufox, para verla
```

## Trawl: que es, donde vive, como esta armado

**Es un servicio completamente aparte**, no vive dentro de `automation-engine`. `automation-engine` es un cliente que le habla por HTTP; Trawl es su propio proyecto, con su propio repo, corriendo en Docker, independiente de este.

### Que es
[germondai/trawl](https://github.com/germondai/trawl): motor de scraping self-hosted, alternativa a FlareSolverr. Resuelve JS challenges y captchas (Cloudflare, Turnstile, reCAPTCHA, hCaptcha) usando Camoufox por dentro. Version instalada: `v1.4.2`.

### Donde vive
```
/Users/sebastianacostamolina/01_Documents/06_onepay/prospector/trawl/
```
Ahi esta su `docker-compose.yml`, su `.env` propio (distinto del `.env` de `automation-engine`), y su propio repo git. Es un proyecto separado que ya tenias instalado antes de esta conversacion.

### Como esta constituido
Dos contenedores Docker, levantados con `docker compose up -d` desde esa carpeta:

| Contenedor | Imagen | Rol |
|---|---|---|
| `trawl-trawl-1` | `ghcr.io/germondai/trawl:latest` | el motor de scraping en si |
| `trawl-redis-1` | `redis:8.8.1-alpine` | cache de sesiones/cookies resueltas, Trawl depende de el |

Puertos expuestos en tu Mac:
- **`8291` -> `8191` (contenedor)**: la API real, la que usa `automation-engine`.
- `8192`: proxy MITM, apagado por defecto (`MITM_PROXY_ENABLED=false`), no se usa aca.

### Como se conecta con automation-engine
En `automation-engine/.env`:
```
TRAWL_URL=http://localhost:8291
```
`src/ejecutores/trawl.py` le hace `POST http://localhost:8291/scrape` con `{"url": "...", "maxTimeout": ...}`, y Trawl devuelve `{"html": "...", "statusCode": 200, ...}` ya resuelto. Sin esta variable puesta, cualquier receta con `motor: trawl` falla con `"TRAWL_URL no configurado"`.

### Comandos utiles para administrarlo
```bash
# ver que esta corriendo
docker ps | grep trawl

# revisar salud
curl http://localhost:8291/health

# reiniciarlo si algo raro pasa
cd /Users/sebastianacostamolina/01_Documents/06_onepay/prospector/trawl
docker compose restart

# apagarlo del todo
docker compose down

# prenderlo de nuevo
docker compose up -d
```

Si `docker ps | grep trawl` no muestra nada corriendo, cualquier receta con `motor: trawl` va a fallar apenas intente conectarse, no por un bug de la receta sino porque el servicio esta apagado.
