import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.camoufox import opciones_camoufox
from src.engine import cargar_receta

receta = cargar_receta(str(settings.dir_recetas / "dian.yaml"))
opciones = opciones_camoufox(True, proxy=settings.camoufox_proxy or None)

with Camoufox(**opciones) as b:
    p = b.new_page()
    datos = {"cedula": "12564660"}
    for i, paso in enumerate(receta.pasos):
        paso = paso.resuelto(datos)
        t0 = time.monotonic()
        try:
            if paso.accion == "navegar":
                p.goto(paso.url)
            elif paso.accion == "clic":
                p.click(paso.selector, force=True, timeout=15000)
            elif paso.accion == "rellenar":
                p.fill(paso.selector, paso.valor)
            elif paso.accion == "esperar":
                p.wait_for_timeout(paso.segundos * 1000)
            elif paso.accion == "ejecutar_js":
                p.evaluate(paso.script)
            elif paso.accion == "presionar":
                p.press(paso.selector, paso.valor)
            elif paso.accion == "extraer":
                texto = p.inner_text(paso.selector, timeout=15000)
                print(f"EXTRAJO: {texto!r}")
            dt = time.monotonic() - t0
            print(f"paso {i} [{paso.accion}] OK en {dt:.1f}s -> url={p.url}")
        except Exception as e:
            dt = time.monotonic() - t0
            print(f"paso {i} [{paso.accion}] FALLO tras {dt:.1f}s: {e!r}")
            print("URL actual:", p.url)
            print("BODY (primeros 800):", p.inner_text("body")[:800].replace("\n", " | "))
            # estado real del boton "Continuar": deshabilitado (rate-limit real
            # de DIAN) vs simplemente lento/no encontrado
            btn = p.query_selector('role=button[name="Continuar"]')
            if btn:
                print("boton Continuar existe. disabled attr:", btn.get_attribute("disabled"))
                print("boton Continuar aria-disabled:", btn.get_attribute("aria-disabled"))
                print("boton Continuar class:", btn.get_attribute("class"))
            else:
                print("boton Continuar NO existe en el DOM en este momento")
            # valor actual del campo de cedula: se lleno de verdad?
            campo = p.query_selector('role=textbox[name="Escriba el número de documento"]')
            if campo:
                print("valor actual del campo cedula:", campo.input_value())
            break
