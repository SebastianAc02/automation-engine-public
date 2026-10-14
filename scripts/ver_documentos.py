import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.camoufox import opciones_camoufox
from src.flujos.scribd import (
    _extraer_texto_scribd,
    _nombre_para_scribd,
    _PATRON_CELULAR_CO,
    _PATRON_ID_SCRIBD,
    _resolver_urls_lote,
)

NOMBRE = "CAROLINA LOPERA GONZALEZ"
opciones = opciones_camoufox(True, perfil="perfiles/google", proxy=settings.camoufox_proxy or None)

with Camoufox(**opciones) as b:
    p = b.pages[0] if b.pages else b.new_page()
    vistos = set()
    for query in [f'site:scribd.com "{_nombre_para_scribd(NOMBRE)}"', f"site:scribd.com {_nombre_para_scribd(NOMBRE)}"]:
        print(f"=== query: {query} ===")
        urls = _resolver_urls_lote(p, b, query, 0)
        for url in urls:
            match = _PATRON_ID_SCRIBD.search(url)
            if not match:
                continue
            doc_id = match.group(1)
            if doc_id in vistos:
                continue
            vistos.add(doc_id)
            try:
                texto = _extraer_texto_scribd(b, p, doc_id)
            except Exception as e:
                print(f"  [{doc_id}] ERROR: {e!r}")
                continue
            numeros = _PATRON_CELULAR_CO.findall(texto or "")
            print(f"  [{doc_id}] {url}")
            print(f"    largo texto: {len(texto or '')} | celulares encontrados: {numeros}")
            print(f"    primeros 300 chars: {(texto or '')[:300]!r}")
            print()
