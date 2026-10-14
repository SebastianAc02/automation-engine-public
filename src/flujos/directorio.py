import re

from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.base import coincidencia_texto
from src.ejecutores.camoufox import opciones_camoufox
from src.ejecutores.captcha import resolver_captcha_si_aparece

_PATRON_NIT = r"NIT[\s\S]{0,30}?(\d{6,})"
_PATRON_TELEFONO_GENERICO = r"Tel[ée]fono[\s\S]{0,30}?(\d{7,})"
_MAX_CANDIDATOS = 2


def _nit_coincide(nit_extraido: str | None, nit_esperado: str) -> bool:
    """El NIT extraido suele traer el digito de verificacion pegado
    (ej: 9004523301 para el NIT base 900452330). Coincide si uno es
    el otro mas un digito de mas al final."""
    a = re.sub(r"\D", "", nit_extraido or "")
    b = re.sub(r"\D", "", nit_esperado or "")
    if not a or not b:
        return False
    return a == b or a.startswith(b) or b.startswith(a)


def _verificar_candidatos(
    pagina,
    selector_resultados: str,
    nit_esperado: str,
    patron_telefono: str = _PATRON_TELEFONO_GENERICO,
) -> dict:
    """Entra a cada candidato con clic real desde la lista de resultados (nunca
    goto directo a la URL: eso "teletransporta" sin referrer y dispara el
    captcha de estos sitios). Para probar el siguiente candidato se vuelve
    atras con go_back en vez de re-navegar a la URL guardada."""
    total = min(pagina.eval_on_selector_all(selector_resultados, "els => els.length"), _MAX_CANDIDATOS)

    if total == 0:
        if resolver_captcha_si_aparece(pagina):
            pagina.wait_for_timeout(1500)
            total = min(pagina.eval_on_selector_all(selector_resultados, "els => els.length"), _MAX_CANDIDATOS)

    if total == 0:
        return {"encontrado": False, "razon": "la busqueda no trajo ningun resultado"}

    candidatos = []
    for i in range(total):
        enlaces = pagina.query_selector_all(selector_resultados)
        url = enlaces[i].get_attribute("href")
        enlaces[i].click(force=True)
        pagina.wait_for_load_state("domcontentloaded")
        pagina.wait_for_timeout(1800)

        if resolver_captcha_si_aparece(pagina):
            pagina.wait_for_timeout(1500)

        texto = pagina.inner_text("body")
        nit = coincidencia_texto(_PATRON_NIT, texto)
        telefono = coincidencia_texto(patron_telefono, texto)
        candidatos.append({"intento": i + 1, "url": url, "nit": nit, "telefono": telefono})

        if _nit_coincide(nit, nit_esperado):
            return {"encontrado": True, "intento": i + 1, "url": url, "nit": nit, "telefono": telefono}

        if i < total - 1:
            pagina.go_back()
            pagina.wait_for_timeout(1200)

    return {
        "encontrado": False,
        "razon": f"el NIT no coincidio en ninguno de los primeros {total} resultados",
        "candidatos": candidatos,
    }


def buscar_empresa_einforma(query: str, nit_esperado: str, headless: bool = True) -> dict:
    opciones = opciones_camoufox(headless, proxy=settings.camoufox_proxy or None)
    with Camoufox(**opciones) as navegador:
        pagina = navegador.new_page()
        # con proxy hay un salto de red extra (VPS->SSH->Mac->sitio): mas margen.
        # sin proxy, timeout corto para fallar rapido contra bloqueo.
        pagina.set_default_timeout(20000 if settings.camoufox_proxy else 8000)
        pagina.goto("https://directorio-empresas.einforma.co/")
        # #search existe en el DOM pero es un buscador oculto de un dropdown del
        # header (display:none); el buscador real y visible de la pagina es
        # #search2, dentro de .r_searchbox.
        pagina.click("#search2", force=True)
        pagina.fill("#search2", query)
        pagina.wait_for_timeout(800)
        pagina.press("#search2", "Enter")
        pagina.wait_for_timeout(2000)

        resultado = _verificar_candidatos(pagina, 'a[href*="informacion-empresa"]', nit_esperado)

        if not headless:
            pagina.wait_for_timeout(3000)
    return resultado


def buscar_empresa_informacolombia(query: str, nit_esperado: str, headless: bool = True) -> dict:
    opciones = opciones_camoufox(headless, proxy=settings.camoufox_proxy or None)
    with Camoufox(**opciones) as navegador:
        pagina = navegador.new_page()
        # con proxy hay un salto de red extra (VPS->SSH->Mac->sitio): mas margen.
        # sin proxy, timeout corto para fallar rapido contra bloqueo.
        pagina.set_default_timeout(20000 if settings.camoufox_proxy else 8000)
        pagina.goto("https://www.informacolombia.com/directorio-empresas")
        pagina.click("#razonsocial", force=True)
        pagina.fill("#razonsocial", query)
        pagina.wait_for_timeout(800)
        pagina.click("#boton_buscar", force=True)
        pagina.wait_for_timeout(2000)

        resultado = _verificar_candidatos(pagina, 'a[href*="informacion-empresa"]', nit_esperado)

        if not headless:
            pagina.wait_for_timeout(3000)
    return resultado


def buscar_empresa_portafolio(query: str, nit_esperado: str, headless: bool = True) -> dict:
    opciones = opciones_camoufox(headless, proxy=settings.camoufox_proxy or None)
    with Camoufox(**opciones) as navegador:
        pagina = navegador.new_page()
        # con proxy hay un salto de red extra (VPS->SSH->Mac->sitio): mas margen.
        # sin proxy, timeout corto para fallar rapido contra bloqueo.
        pagina.set_default_timeout(20000 if settings.camoufox_proxy else 8000)
        pagina.goto("https://empresas.portafolio.co/")
        pagina.click('input[name="q"]:visible', force=True)
        pagina.fill('input[name="q"]:visible', query)
        pagina.wait_for_timeout(800)
        pagina.click("button.btn_buscar:visible", force=True)
        pagina.wait_for_timeout(2000)

        resultado = _verificar_candidatos(
            pagina, 'a[href$=".html"]', nit_esperado, patron_telefono=r"TEL[ÉE]FONO:\s*(\d{7,})"
        )

        if not headless:
            pagina.wait_for_timeout(3000)
    return resultado
