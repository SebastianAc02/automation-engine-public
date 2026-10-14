import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.camoufox import opciones_camoufox

query = 'site:scribd.com "AGUSTIN AYALA LOPEZ"'
opciones = opciones_camoufox(True, proxy=settings.camoufox_proxy or None)

with Camoufox(**opciones) as b:
    p = b.new_page()
    print("=== GOOGLE (natural) ===")
    p.goto("https://www.google.com/")
    p.wait_for_timeout(2000)
    p.fill('textarea[name="q"], input[name="q"]', query)
    p.keyboard.press("Enter")
    p.wait_for_timeout(3000)
    body = p.inner_text("body")
    print("bloqueado:", "tráfico inusual" in body or "unusual traffic" in body.lower())
    print(body[:500])
    ofuscados = p.eval_on_selector_all('a[href*="/goto?url="]', "els => els.map(e => e.href)")
    print("links /goto?url= encontrados:", len(ofuscados))
    hrefs = p.eval_on_selector_all("a", "els => els.map(e => e.href)")
    scribd_hrefs = [h for h in hrefs if "scribd.com" in h]
    print("hrefs con scribd.com (cualquier formato):", scribd_hrefs[:5])

    print()
    print("=== DDG ===")
    p.goto(f"https://html.duckduckgo.com/html/?q={quote(query)}")
    p.wait_for_timeout(2500)
    body2 = p.inner_text("body")
    print(body2[:500])
    hrefs2 = p.eval_on_selector_all("a.result__a", "els => els.map(e => e.href)")
    print("a.result__a encontrados:", len(hrefs2))
    hrefs_all = p.eval_on_selector_all("a", "els => els.map(e => e.href)")
    scribd2 = [h for h in hrefs_all if "scribd" in h]
    print("hrefs con scribd (cualquier clase):", scribd2[:5])
