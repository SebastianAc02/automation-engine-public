import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.camoufox import opciones_camoufox
from src.flujos.scribd import _extraer_texto_scribd, _PATRON_CELULAR_CO, _PATRON_ID_SCRIBD, _recolectar_urls_scribd

CEDULA = "66803475"
opciones = opciones_camoufox(True, perfil="perfiles/google", proxy=settings.camoufox_proxy or None)

with Camoufox(**opciones) as b:
    p = b.pages[0] if b.pages else b.new_page()
    urls = _recolectar_urls_scribd(p, b, CEDULA)
    print(f"total documentos unicos de scribd.com encontrados: {len(urls)}")
    for url in urls:
        match = _PATRON_ID_SCRIBD.search(url)
        doc_id = match.group(1)
        try:
            texto = _extraer_texto_scribd(b, p, doc_id)
        except Exception as e:
            print(f"  [{doc_id}] ERROR: {e!r}")
            continue
        numeros = _PATRON_CELULAR_CO.findall(texto or "")
        print(f"  [{doc_id}] {url}")
        print(f"    celulares: {numeros}")
        print(f"    primeros 200 chars: {(texto or '')[:200]!r}")
