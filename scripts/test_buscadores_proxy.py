import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.camoufox import opciones_camoufox
from src.flujos.scribd import _resolver_urls_lote
import src.flujos.scribd as scribd_mod

query = 'site:scribd.com "AGUSTIN AYALA LOPEZ"'

for buscador in ["google", "ddg", "bing"]:
    scribd_mod._BUSCADOR = buscador
    opciones = opciones_camoufox(True, proxy=settings.camoufox_proxy or None)
    try:
        with Camoufox(**opciones) as b:
            p = b.new_page()
            urls = _resolver_urls_lote(p, b, query, 0)
            print(f"{buscador}: {len(urls)} urls -> {urls[:3]}")
    except Exception as e:
        print(f"{buscador}: ERROR {e!r}")
