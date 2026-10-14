import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.camoufox import opciones_camoufox
from src.flujos.scribd import _PATRON_ID_SCRIBD, _resolver_ofuscados

CEDULA = "66803475"
opciones = opciones_camoufox(True, perfil="perfiles/google", proxy=settings.camoufox_proxy or None)


def buscar(query: str, pagina, contexto):
    pagina.goto("https://www.google.com/")
    pagina.wait_for_timeout(2000)
    pagina.fill('textarea[name="q"], input[name="q"]', query)
    pagina.keyboard.press("Enter")
    pagina.wait_for_timeout(3000)
    urls = _resolver_ofuscados(pagina, contexto)
    scribd_urls = [u for u in urls if _PATRON_ID_SCRIBD.search(u)]
    return urls, scribd_urls


with Camoufox(**opciones) as b:
    p = b.pages[0] if b.pages else b.new_page()

    print(f'=== query CON comillas: site:scribd.com "{CEDULA}" ===')
    urls, scribd_urls = buscar(f'site:scribd.com "{CEDULA}"', p, b)
    print(f"total urls: {len(urls)}, scribd docs: {len(scribd_urls)}")
    for u in scribd_urls[:20]:
        print("  ", u)

    print()
    print(f"=== query SIN comillas: site:scribd.com {CEDULA} ===")
    urls2, scribd_urls2 = buscar(f"site:scribd.com {CEDULA}", p, b)
    print(f"total urls: {len(urls2)}, scribd docs: {len(scribd_urls2)}")
    for u in scribd_urls2[:20]:
        print("  ", u)
