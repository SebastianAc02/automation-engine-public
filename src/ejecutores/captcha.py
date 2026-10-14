"""Resuelve reCAPTCHA v2 / hCaptcha via 2captcha.com cuando un flujo se topa
con uno. No se usa proactivamente: los flujos de directorios evitan el
captcha navegando por clic en vez de goto directo (ver directorio.py). Esto
es la red de respaldo para cuando igual aparece.
"""

from twocaptcha import TwoCaptcha

from config.settings import settings


def hay_captcha(pagina) -> str | None:
    """Devuelve 'recaptcha', 'hcaptcha' o None segun lo que detecte en la pagina."""
    if pagina.query_selector("iframe[src*='recaptcha']") or pagina.query_selector("div.g-recaptcha"):
        return "recaptcha"
    if pagina.query_selector("iframe[src*='hcaptcha']") or pagina.query_selector("div.h-captcha"):
        return "hcaptcha"
    return None


def _sitekey(pagina, selector_div: str) -> str | None:
    elemento = pagina.query_selector(selector_div)
    if elemento:
        return elemento.get_attribute("data-sitekey")
    return None


_TEXTOS_ENVIAR = ["verificar", "continuar", "enviar", "submit", "confirmar"]


def _enviar_formulario_si_existe(pagina) -> None:
    """Tras inyectar el token, muchos sitios (ej. informacolombia) no
    reaccionan solos al callback: hay que darle clic a un boton de
    verificacion/envio explicito. Busca uno por texto conocido y lo clickea."""
    botones = pagina.query_selector_all("button, input[type='submit'], input[type='button']")
    for boton in botones:
        texto = (boton.get_attribute("value") or boton.inner_text() or "").strip().lower()
        if any(t in texto for t in _TEXTOS_ENVIAR):
            boton.click(force=True)
            pagina.wait_for_load_state("domcontentloaded")
            return


def resolver_captcha_si_aparece(pagina, timeout: int = 120) -> bool:
    """Si hay captcha en la pagina, lo resuelve inyectando el token de
    2captcha y devuelve True. Si no hay captcha o no hay API key configurada,
    devuelve False sin hacer nada."""
    if not settings.twocaptcha_api_key:
        return False

    tipo = hay_captcha(pagina)
    if tipo is None:
        return False

    solver = TwoCaptcha(settings.twocaptcha_api_key, recaptchaTimeout=timeout, defaultTimeout=timeout)
    url = pagina.url

    if tipo == "recaptcha":
        sitekey = _sitekey(pagina, "div.g-recaptcha")
        if not sitekey:
            return False
        resultado = solver.recaptcha(sitekey=sitekey, url=url)
        token = resultado["code"]
        pagina.evaluate(
            """(token) => {
                document.querySelectorAll('textarea#g-recaptcha-response, textarea[name="g-recaptcha-response"]')
                    .forEach(el => { el.value = token; el.style.display = 'block'; });
                if (typeof window.___grecaptcha_cfg === 'object') {
                    Object.values(window.___grecaptcha_cfg.clients || {}).forEach(client => {
                        Object.values(client).forEach(widget => {
                            if (widget && typeof widget.callback === 'function') widget.callback(token);
                        });
                    });
                }
            }""",
            token,
        )
        _enviar_formulario_si_existe(pagina)
        return True

    if tipo == "hcaptcha":
        sitekey = _sitekey(pagina, "div.h-captcha")
        if not sitekey:
            return False
        resultado = solver.hcaptcha(sitekey=sitekey, url=url)
        token = resultado["code"]
        pagina.evaluate(
            """(token) => {
                document.querySelectorAll('textarea[name="h-captcha-response"], textarea[name="g-recaptcha-response"]')
                    .forEach(el => { el.value = token; });
            }""",
            token,
        )
        _enviar_formulario_si_existe(pagina)
        return True

    return False
