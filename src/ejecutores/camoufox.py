import json

import anthropic
from camoufox.sync_api import Camoufox
from loguru import logger

from config.settings import settings
from src.ejecutores.base import EjecutorBase, coincidencia_texto, valores_coinciden
from src.ejecutores.captcha import resolver_captcha_si_aparece
from src.models import Paso, Receta, Resultado


def opciones_camoufox(headless: bool, perfil: str | None = None, proxy: str | None = None) -> dict:
    opciones = dict(headless=headless, humanize=True, os="macos", geoip=True)
    if perfil:
        opciones["persistent_context"] = True
        opciones["user_data_dir"] = perfil
    if proxy:
        opciones["proxy"] = {"server": proxy}
    return opciones


class _FalloPaso(Exception):
    """Interrumpe la receta con el diagnostico ya armado (texto de la pagina
    en el momento del fallo). Se usa para poder lanzar el fallo desde
    cualquier profundidad de recursion (dentro de repetir_hasta/condicional)
    y que el nivel raiz lo capture una sola vez."""

    def __init__(self, mensaje: str):
        self.mensaje = mensaje


class CamoufoxEjecutor(EjecutorBase):
    def ejecutar(self, receta: Receta, datos: dict) -> Resultado:
        extraido: dict = {}
        opciones = opciones_camoufox(receta.headless, receta.perfil, settings.camoufox_proxy or None)

        with Camoufox(**opciones) as navegador:
            pagina = navegador.pages[0] if receta.perfil and navegador.pages else navegador.new_page()
            total_pasos = len(receta.pasos)
            try:
                for indice, paso in enumerate(receta.pasos):
                    self._ejecutar_paso(pagina, paso.resuelto(datos), extraido, datos, receta.nombre, indice, total_pasos)
            except _FalloPaso as fallo:
                return Resultado(exito=False, datos=extraido, error=fallo.mensaje)

            if not receta.headless:
                # pausa breve para ver el resultado final en pantalla antes
                # de cerrar, no un bloqueo largo (rompe el flujo cuando se
                # encadenan varias etapas visibles seguidas, ej. demo_full.py).
                pagina.wait_for_timeout(3000)

        return Resultado(exito=True, datos=extraido)

    def _ejecutar_paso(
        self, pagina, paso: Paso, extraido: dict, datos: dict,
        nombre_receta: str, indice: int, total_pasos: int,
    ) -> None:
        try:
            if paso.accion == "navegar":
                pagina.goto(paso.url)
            elif paso.accion == "clic":
                # .first en vez de page.click(): un selector con mas de una
                # coincidencia (ej. "text=Ver informacion" repetido en la
                # pagina) rompe page.click() en modo strict; .first toma el
                # primero de forma predecible.
                pagina.locator(paso.selector).first.click(force=True)
            elif paso.accion == "rellenar":
                pagina.fill(paso.selector, paso.valor)
            elif paso.accion == "extraer":
                texto = pagina.inner_text(paso.selector)
                extraido[paso.salida or paso.selector] = coincidencia_texto(paso.patron, texto) if paso.patron else texto
            elif paso.accion == "esperar":
                pagina.wait_for_timeout(paso.segundos * 1000)
            elif paso.accion == "ejecutar_js":
                pagina.evaluate(paso.script)
            elif paso.accion == "presionar":
                pagina.press(paso.selector, paso.valor)
            elif paso.accion == "esperar_texto":
                self._esperar_texto(pagina, paso)
            elif paso.accion == "estructurar_llm":
                self._estructurar_llm(paso, extraido)
            elif paso.accion == "resolver_captcha":
                # generico: si hay un recaptcha/hcaptcha bloqueando (ej. la
                # busqueda no trajo resultados por rate-limit del sitio), lo
                # resuelve via 2captcha.com. No hace nada si no hay captcha.
                resolver_captcha_si_aparece(pagina)
            elif paso.accion == "condicional":
                # ejecuta paso.pasos solo si `si_vacio` (un selector) no
                # tiene ningun elemento en la pagina ahora mismo.
                if paso.si_vacio and pagina.locator(paso.si_vacio).count() == 0:
                    for sub in paso.pasos or []:
                        self._ejecutar_paso(pagina, sub.resuelto(datos), extraido, datos, nombre_receta, indice, total_pasos)
            elif paso.accion == "repetir_hasta":
                self._repetir_hasta(pagina, paso, extraido, datos, nombre_receta, indice, total_pasos)

            logger.info(f"[{nombre_receta}] paso {indice + 1}/{total_pasos} completado: {paso.accion}")
        except _FalloPaso:
            raise
        except Exception as e:
            # diagnostico: sin esto, cualquier fallo de un paso (selector
            # cambiado, timeout, la pagina mostro algo distinto a lo
            # esperado) queda indistinguible de un negativo real del sitio.
            # Se captura el texto visible de la pagina en el momento del
            # fallo para poder diferenciar despues.
            texto_pagina = ""
            try:
                texto_pagina = pagina.inner_text("body")[:1500]
            except Exception:
                pass
            raise _FalloPaso(
                f"fallo en paso {indice} ({paso.accion} / {paso.selector or paso.url}): "
                f"{e!r}\n--- texto visible de la pagina en ese momento ---\n{texto_pagina}"
            ) from e

    def _esperar_texto(self, pagina, paso: Paso) -> None:
        # generico y reutilizable: espera en poll (1s) a que `patron` (un
        # substring, no regex) aparezca en el texto visible de la pagina.
        # Para SPAs que cargan contenido async despues de un clic, donde un
        # wait_for_timeout fijo es o muy corto (falla) o muy largo
        # (desperdicia tiempo en el caso rapido).
        max_segundos = int(paso.segundos or 20)
        for _ in range(max_segundos):
            if paso.patron in pagina.inner_text("body"):
                return
            pagina.wait_for_timeout(1000)
        raise TimeoutError(f"esperar_texto: '{paso.patron}' no aparecio tras {max_segundos}s")

    def _estructurar_llm(self, paso: Paso, extraido: dict) -> None:
        # generico: toma un texto ya extraido (paso.selector = la clave en
        # `extraido`) y lo estructura con Claude usando paso.script como
        # prompt de sistema. El prompt debe pedir explicitamente "responde
        # solo con JSON valido, sin texto adicional". Si el LLM no devuelve
        # JSON parseable, se guarda el texto crudo bajo salida+'_crudo' para
        # poder depurar sin perder el intento.
        texto_fuente = extraido.get(paso.selector, "")
        cliente = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        respuesta = cliente.messages.create(
            model=settings.modelo_llm,
            max_tokens=4000,
            system=paso.script,
            messages=[{"role": "user", "content": texto_fuente}],
        )
        # claude-sonnet-5 puede devolver un ThinkingBlock antes del TextBlock
        # real; no asumir que content[0] es texto.
        bloque_texto = next(b for b in respuesta.content if b.type == "text")
        texto_json = bloque_texto.text.strip()
        # a veces el modelo envuelve el JSON en ```json ... ``` pese a que el
        # prompt pide "sin markdown".
        if texto_json.startswith("```"):
            texto_json = texto_json.split("```")[1]
            if texto_json.startswith("json"):
                texto_json = texto_json[4:]
            texto_json = texto_json.strip()
        clave = paso.salida or "estructurado"
        try:
            extraido[clave] = json.loads(texto_json)
        except json.JSONDecodeError:
            extraido[f"{clave}_crudo"] = texto_json

    def _repetir_hasta(
        self, pagina, paso: Paso, extraido: dict, datos: dict,
        nombre_receta: str, indice_padre: int, total_pasos: int,
    ) -> None:
        # entra a cada candidato con clic real desde la lista de resultados
        # (nunca goto directo a la url: eso "teletransporta" sin referrer y
        # dispara captcha en varios directorios), corre paso.pasos sobre esa
        # pagina de detalle, evalua parar_si contra lo que esos sub-pasos
        # dejaron en `extraido`, y si no coincide vuelve atras (go_back) a
        # intentar con el siguiente candidato. `encontrado` en el resultado
        # dice si alguna iteracion cumplio parar_si.
        max_intentos = paso.max_intentos or 2
        total_candidatos = min(pagina.locator(paso.selector).count(), max_intentos)
        extraido["encontrado"] = False
        extraido["candidatos"] = []

        for intento in range(total_candidatos):
            enlaces = pagina.locator(paso.selector)
            url_candidato = enlaces.nth(intento).get_attribute("href")
            enlaces.nth(intento).click(force=True)
            pagina.wait_for_load_state("domcontentloaded")
            pagina.wait_for_timeout(1500)

            sub_extraido: dict = {}
            for sub in paso.pasos or []:
                self._ejecutar_paso(pagina, sub.resuelto(datos), sub_extraido, datos, nombre_receta, indice_padre, total_pasos)

            sub_extraido["url"] = url_candidato
            extraido["candidatos"].append(sub_extraido)

            if paso.parar_si:
                valor_extraido = sub_extraido.get(paso.parar_si.campo)
                if valores_coinciden(valor_extraido, paso.parar_si.igual_a, paso.parar_si.tolerancia_digito_extra):
                    extraido.update(sub_extraido)
                    extraido["encontrado"] = True
                    return

            if intento < total_candidatos - 1:
                pagina.go_back()
                pagina.wait_for_timeout(1200)
