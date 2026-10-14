import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from html.parser import HTMLParser
from urllib.parse import quote

import httpx
from camoufox.sync_api import Camoufox

from config.settings import settings
from src.ejecutores.camoufox import opciones_camoufox

_HEADERS_EMBED = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
}
_N_HILOS_FETCH = 5

_PATRON_ID_SCRIBD = re.compile(r"scribd\.com/(?:document|doc)/(\d+)")
# el downloader solo entiende www.scribd.com; los buscadores devuelven
# es./pt./de./fr. segun el idioma de la busqueda y con esos falla.
_PATRON_SUBDOMINIO_SCRIBD = re.compile(r"https?://[a-z]{2,3}\.scribd\.com/")
# Sufijos de forma juridica: los documentos de scribd casi nunca escriben el
# "SAS/LTDA/S.A.S." exacto, asi que buscar con la comilla exacta del nombre legal
# completo mata los resultados. Se quitan antes de armar el query.
_SUFIJOS_LEGALES = re.compile(
    r"\b(S\.?\s?A\.?\s?S\.?|LTDA\.?|LIMITADA|E\.?\s?S\.?\s?P\.?|S\.?\s?A\.?|BIC|ZOMAC|"
    r"S\.?\s?EN\s?C\.?|Y?\s?CIA\.?|E\.?\s?U\.?)\b",
    re.IGNORECASE,
)


def _nombre_para_scribd(nombre: str) -> str:
    limpio = _SUFIJOS_LEGALES.sub(" ", nombre)
    return re.sub(r"\s+", " ", limpio).strip(" .,-")
# Perfil persistente de Google. Configurable por entorno para que cada worker
# paralelo use su propia copia y no se peleen el lock del perfil de Firefox.
_PERFIL_GOOGLE = os.environ.get("RUES_PERFIL_GOOGLE", "perfiles/google")
# Buscador: google (default, IP residencial), o ddg/bing (para el VPS, cuya IP
# de datacenter Google bloquea). ddg y bing responden bien desde el datacenter.
_BUSCADOR = os.environ.get("RUES_BUSCADOR", "google")


class _ParserCapasDeTexto(HTMLParser):
    """Extrae el texto de cada <div class=text_layer> del HTML del embed de Scribd.
    Server-rendered: no hace falta ejecutar JS ni cargar la pagina en un navegador."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.profundidad = 0
        self.paginas = []
        self.actual = []

    def handle_starttag(self, tag, attrs):
        if tag != "div":
            return
        if self.profundidad == 0 and dict(attrs).get("class", "").split()[:1] == ["text_layer"]:
            if self.actual:
                self.paginas.append("".join(self.actual).strip())
                self.actual = []
            self.profundidad = 1
        elif self.profundidad > 0:
            self.profundidad += 1

    def handle_endtag(self, tag):
        if tag == "div" and self.profundidad > 0:
            self.profundidad -= 1

    def handle_data(self, data):
        if self.profundidad > 0:
            self.actual.append(data)

    def cerrar(self) -> list[str]:
        self.close()
        if self.actual:
            self.paginas.append("".join(self.actual).strip())
        return self.paginas


def _resolver_urls_google(pagina, contexto, query: str) -> list[str]:
    pagina.goto("https://www.google.com/")
    pagina.wait_for_timeout(2000)
    pagina.fill('textarea[name="q"], input[name="q"]', query)
    pagina.keyboard.press("Enter")
    pagina.wait_for_timeout(3000)
    return _resolver_ofuscados(pagina, contexto)


def _resolver_urls_google_lote(pagina, contexto, query: str, inicio: int) -> list[str]:
    """Trae una pagina especifica de resultados. El primer lote (inicio=0)
    navega como humano (home -> escribe -> Enter): ir directo a /search?q=
    dispara el bloqueo de "trafico inusual" mucho antes que abrir el home
    primero. Lotes siguientes si van por URL directa con &start=, porque ya
    hay una sesion "calentada" desde el home."""
    if inicio == 0:
        return _resolver_urls_google(pagina, contexto, query)
    pagina.goto(f"https://www.google.com/search?q={quote(query)}&start={inicio}")
    pagina.wait_for_timeout(2500)
    return _resolver_ofuscados(pagina, contexto)


def _resolver_urls_ddg(pagina, contexto, query: str, inicio: int) -> list[str]:
    return [u for u, _ in _resolver_ddg_con_snippet(pagina, query, inicio)]


def _resolver_ddg_con_snippet(pagina, query: str, inicio: int) -> list[tuple[str, str]]:
    # DuckDuckGo real (duckduckgo.com, con JS), no la version "html.duckduckgo.com/html/"
    # (server-rendered lite): esa version lite NO tiene los mismos resultados que el
    # sitio real, confirmado en vivo (el sitio real encontro un documento que la lite
    # devolvia 0 resultados para la misma query). Selector confirmado: 'article h2 a'
    # para el link, 'article' completo para el snippet (texto de la vista previa).
    #
    # OJO, hallazgo clave: el snippet que DDG muestra puede traer texto de paginas
    # de scribd que nosotros NO logramos leer (documentos con muro de suscripcion,
    # solo dejan ver las primeras ~4 paginas gratis). El buscador indexo el
    # documento completo; nuestro fetch directo no. Por eso el snippet se revisa
    # ANTES de intentar abrir el documento: puede tener el dato aunque el
    # documento en si nos quede bloqueado.
    if inicio > 0:
        return []
    pagina.goto(f"https://duckduckgo.com/?q={quote(query)}")
    pagina.wait_for_timeout(2500)
    return pagina.evaluate("""
        () => Array.from(document.querySelectorAll('article')).map(art => {
            const a = art.querySelector('h2 a');
            return a ? [a.href, art.innerText] : null;
        }).filter(Boolean)
    """)


def _resolver_urls_bing(pagina, contexto, query: str, inicio: int) -> list[str]:
    pagina.goto(f"https://www.bing.com/search?q={quote(query)}&first={inicio + 1}")
    pagina.wait_for_timeout(2500)
    return pagina.eval_on_selector_all("li.b_algo h2 a", "els => els.map(e => e.href)")


def _resolver_urls_lote(pagina, contexto, query: str, inicio: int) -> list[str]:
    if _BUSCADOR == "ddg":
        return _resolver_urls_ddg(pagina, contexto, query, inicio)
    if _BUSCADOR == "bing":
        return _resolver_urls_bing(pagina, contexto, query, inicio)
    return _resolver_urls_google_lote(pagina, contexto, query, inicio)


def _resolver_ofuscados(pagina, contexto) -> list[str]:
    ofuscados = pagina.eval_on_selector_all('a[href*="/goto?url="]', "els => els.map(e => e.href)")
    resueltas = []
    for href in dict.fromkeys(ofuscados):
        respuesta = contexto.request.get(href, max_redirects=0)
        destino = respuesta.headers.get("location")
        if destino:
            resueltas.append(destino)
    return resueltas


def _fetch_embed_paralelo(doc_id: str) -> tuple[str, str | None]:
    """Version paralelizable de la primera mitad de _extraer_texto_scribd:
    un GET plano con httpx (sin pasar por Playwright, asi que N hilos
    pueden llamarla a la vez sin pisarse). Devuelve (doc_id, texto) si lo
    logro server-rendered, o (doc_id, None) si el sitio pidio "Client
    Challenge" (necesita navegador real, se resuelve despues en serie)."""
    url = f"https://www.scribd.com/embeds/{doc_id}/content"
    try:
        respuesta = httpx.get(url, headers=_HEADERS_EMBED, timeout=15, follow_redirects=True)
        html = respuesta.text
    except Exception:
        return doc_id, None
    if "Client Challenge" in html:
        return doc_id, None
    parser = _ParserCapasDeTexto()
    parser.feed(html)
    paginas = parser.cerrar()
    return doc_id, "\n\n".join(p for p in paginas if p)


def _extraer_texto_scribd(contexto, pagina, doc_id: str) -> str:
    url = f"https://www.scribd.com/embeds/{doc_id}/content"
    respuesta = contexto.request.get(url)
    html = respuesta.text()

    if "Client Challenge" in html:
        # Scribd exige resolver un challenge JS antes de servir el contenido
        # (aparece cuando hay muchas peticiones HTTP seguidas sin navegador real
        # detras). Fallback a navegacion real, que ejecuta el JS y lo resuelve.
        pagina.goto(url)
        pagina.wait_for_timeout(2500)
        paginas = pagina.eval_on_selector_all(".text_layer", "els => els.map(e => e.textContent.trim())")
        return "\n\n".join(p for p in paginas if p)

    parser = _ParserCapasDeTexto()
    parser.feed(html)
    paginas = parser.cerrar()
    return "\n\n".join(p for p in paginas if p)


def buscar_y_extraer_scribd(query: str, headless: bool = True) -> list[dict]:
    """Busca en Google, resuelve los links reales de scribd.com encontrados y extrae el texto completo de cada documento via el embed publico."""
    opciones = opciones_camoufox(headless, perfil=_PERFIL_GOOGLE, proxy=settings.camoufox_proxy or None)

    with Camoufox(**opciones) as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()
        urls = _resolver_urls_google(pagina, contexto, query)

        vistos = set()
        documentos = []
        for url in urls:
            match = _PATRON_ID_SCRIBD.search(url)
            if not match:
                continue
            doc_id = match.group(1)
            if doc_id in vistos:
                continue
            vistos.add(doc_id)

            try:
                texto = _extraer_texto_scribd(contexto, pagina, doc_id)
            except Exception as error:
                documentos.append({"id": doc_id, "url": url, "error": str(error)})
                continue
            documentos.append({"id": doc_id, "url": url, "texto": texto})

        if not headless:
            pagina.wait_for_timeout(3000)

    return documentos


_PATRON_CELULAR_CO = re.compile(r"(?<!\d)3\d{9}(?!\d)")
# tope total de documentos de scribd revisados por empresa, sumando las dos
# variantes de query (con y sin comillas). No es por-variante: si la primera
# variante ya trae 20, no se llega a probar la segunda.
_MAX_DOCUMENTOS = 20


def _variantes_query(nombre: str) -> list[str]:
    limpio = _nombre_para_scribd(nombre)
    # con comillas: frase exacta, mas precisa pero mas restrictiva.
    # sin comillas: el motor la trata como AND de palabras sueltas, menos
    # exacta pero puede sacar documentos donde el nombre viene en otro orden.
    return [f'site:scribd.com "{limpio}"', f"site:scribd.com {limpio}"]


def _recolectar_urls_scribd(pagina, contexto, nombre: str) -> list[str]:
    """Version sin snippets (compatibilidad). Ver _recolectar_scribd_con_snippet
    para la version que ademas revisa el texto de vista previa de DDG."""
    return [url for url, _ in _recolectar_scribd_con_snippet(pagina, contexto, nombre)]


def _recolectar_scribd_con_snippet(pagina, contexto, nombre: str) -> list[tuple[str, str]]:
    """Junta las urls de scribd.com de los 3 motores (Google, DuckDuckGo,
    Bing) x 2 variantes de query (con/sin comillas) = hasta 6 busquedas.
    Primero se RECOLECTA todo, deduplicado por doc_id; el llamador procesa
    (extrae texto de) el conjunto combinado una sola vez despues, no
    intercalado por motor. Para DDG se guarda tambien el snippet (texto de
    vista previa), que puede traer datos de paginas que el fetch directo del
    documento no logra leer (muro de suscripcion de scribd)."""
    vistos: dict[str, tuple[str, str]] = {}  # doc_id -> (url, snippet)
    for query in _variantes_query(nombre):
        pares: list[tuple[str, str]] = []
        try:
            pares += _resolver_ddg_con_snippet(pagina, query, 0)
        except Exception:
            pass
        for url in _try(lambda: _resolver_urls_google(pagina, contexto, query)):
            pares.append((url, ""))
        for url in _try(lambda: _resolver_urls_bing(pagina, contexto, query, 0)):
            pares.append((url, ""))
        for url, snippet in pares:
            match = _PATRON_ID_SCRIBD.search(url)
            if not match:
                continue
            doc_id = match.group(1)
            if doc_id not in vistos or (snippet and not vistos[doc_id][1]):
                vistos[doc_id] = (url, snippet)
    return list(vistos.values())


def _try(fn):
    try:
        return fn()
    except Exception:
        return []


def buscar_telefono_scribd(nombre: str, ultimos4: list[str], headless: bool = True) -> dict:
    """Recolecta primero todas las urls de scribd.com que traen Google,
    DuckDuckGo y Bing (2 variantes de query cada uno: con y sin comillas),
    deduplicadas por doc_id. Despues procesa el conjunto combinado, hasta 20
    documentos: extrae el texto de cada uno y busca numeros celulares
    colombianos (3 + 9 digitos), separando los que coinciden en los ultimos 4
    digitos con alguno de `ultimos4` de los que solo parecen celular real sin
    coincidir. Para en cuanto encuentra una coincidencia."""
    opciones = opciones_camoufox(headless, perfil=_PERFIL_GOOGLE, proxy=settings.camoufox_proxy or None)

    coincidencias = []
    posibles = []
    numeros_vistos = set()
    documentos_revisados = 0

    with Camoufox(**opciones) as contexto:
        pagina = contexto.pages[0] if contexto.pages else contexto.new_page()

        urls_con_snippet = _recolectar_scribd_con_snippet(pagina, contexto, nombre)
        docs_encontrados_total = len(urls_con_snippet)  # total de docs unicos recolectados, para el reporte

        def _registrar(numero: str, url: str):
            if numero in numeros_vistos:
                return
            numeros_vistos.add(numero)
            entrada = {"numero": numero, "documento": url}
            grupo = next((g for g in ultimos4 if numero.endswith(g)), None)
            if grupo:
                entrada["coincide_con"] = grupo
                coincidencias.append(entrada)
            else:
                posibles.append(entrada)

        # 1. Revisa PRIMERO los snippets de todos los documentos recolectados
        # (barato, ya los tenemos, sin abrir nada). Puede traer datos de
        # paginas que el fetch directo del documento no logra leer.
        for url, snippet in urls_con_snippet:
            for numero in _PATRON_CELULAR_CO.findall(snippet or ""):
                _registrar(numero, url)
            if coincidencias:
                break

        # 2. Si el snippet no dio match, abre los documentos. El fetch del
        # embed es HTTP plano (httpx), no toca Playwright, asi que se
        # paraleliza con hilos; solo lo que pida "Client Challenge" cae a
        # navegacion real, en serie (comparte el unico `pagina`/`contexto`).
        pendientes = urls_con_snippet[:_MAX_DOCUMENTOS]
        url_por_doc_id = {}
        for url, _ in pendientes:
            match = _PATRON_ID_SCRIBD.search(url)
            url_por_doc_id[match.group(1)] = url
        documentos_revisados = len(url_por_doc_id)

        challenge = []
        with ThreadPoolExecutor(max_workers=_N_HILOS_FETCH) as pool:
            for doc_id, texto in pool.map(_fetch_embed_paralelo, url_por_doc_id.keys()):
                if coincidencias:
                    break
                if texto is None:
                    challenge.append(doc_id)
                    continue
                for numero in _PATRON_CELULAR_CO.findall(texto):
                    _registrar(numero, url_por_doc_id[doc_id])

        # documentos que pidieron Client Challenge: fallback a navegacion
        # real, en serie (comparten el navegador con el resto del flujo).
        for doc_id in challenge:
            if coincidencias:
                break
            try:
                texto = _extraer_texto_scribd(contexto, pagina, doc_id)
            except Exception:
                continue
            for numero in _PATRON_CELULAR_CO.findall(texto or ""):
                _registrar(numero, url_por_doc_id[doc_id])

        if not headless:
            pagina.wait_for_timeout(3000)

        if not coincidencias:
            resultado_ultima_milla = {"urls_no_confirmadas": [url_por_doc_id[d] for d in url_por_doc_id]}
        else:
            resultado_ultima_milla = None

    return {
        "encontrado": bool(coincidencias),
        "razon": None if coincidencias else "no se encontro en los primeros "
        f"{documentos_revisados} documentos revisados ({docs_encontrados_total} lote(s))",
        "coincidencias": coincidencias,
        "posibles": posibles,
        "documentos_revisados": documentos_revisados,
        "docs_encontrados_total": docs_encontrados_total,
        "_ultima_milla": resultado_ultima_milla,
    }


def _descargar_via_servicio(url: str, servicio_url: str, timeout: int = 300) -> str | None:
    """Le pide al servicio de descarga completa (el wrapper HTTP sobre el
    downloader de terceros, corriendo en la maquina del operador) que baje
    el PDF completo del documento. Devuelve la ruta local del PDF o None si
    fallo. El servicio corre bajo un lock (una descarga a la vez del lado
    del servidor), asi que varias llamadas concurrentes quedan en fila ahi,
    no se pisan.

    OJO: el downloader solo entiende www.scribd.com. Los buscadores
    devuelven casi todo como es.scribd.com (o pt./de./fr.) porque las
    busquedas son en espanol, y con ese subdominio el script falla en ~3s
    sin generar PDF. Medido: mismo documento, www -> OK en 14s,
    es -> FALLO. Por eso se normaliza el dominio antes de pedirlo."""
    url = _PATRON_SUBDOMINIO_SCRIBD.sub("https://www.scribd.com/", url)
    try:
        respuesta = httpx.post(f"{servicio_url}/descargar", json={"url": url}, timeout=timeout)
        datos = respuesta.json()
    except Exception:
        return None
    return datos.get("pdf_path")


def _extraer_texto_pdf(ruta: str) -> str:
    """Texto crudo del PDF, sin pasar por ningun modelo: Scribd revuelve las
    LETRAS con una fuente de glifos sustituidos (proteccion anti-copiado),
    pero los DIGITOS quedan intactos. Un regex sobre este texto encuentra
    los numeros de celular igual, aunque el resto se vea como jerigonza."""
    import pypdf

    lector = pypdf.PdfReader(ruta)
    return "\n".join(pagina.extract_text() or "" for pagina in lector.pages)


def ultima_milla_scribd(
    urls: list[str], ultimos4: list[str], servicio_url: str = "http://localhost:5055", max_paralelo: int = 3
) -> dict:
    """Descarga el PDF completo (via el servicio del operador, bypass del
    muro de paywall que limita el fetch gratis a ~4 paginas) de cada url
    pendiente, uno a la vez del lado del servidor pero disparados en
    paralelo desde aca (quedan en fila si el servidor no puede en paralelo
    de verdad). Extrae texto crudo, busca el patron de celular por regex
    (nada de LLM: son muchos documentos, no vale la pena el gasto de
    tokens), y BORRA el PDF descargado apenas lo procesa, haya o no match.
    Para en el primer match."""
    coincidencias = []
    posibles = []
    numeros_vistos = set()

    def _procesar_uno(url: str) -> dict:
        ruta = _descargar_via_servicio(url, servicio_url)
        if not ruta:
            return {"url": url, "error": "no se pudo descargar via el servicio"}
        try:
            texto = _extraer_texto_pdf(ruta)
            numeros = _PATRON_CELULAR_CO.findall(texto)
            return {"url": url, "numeros": numeros}
        except Exception as e:
            return {"url": url, "error": repr(e)}
        finally:
            # limpieza obligatoria: nunca dejar el PDF acumulado en disco.
            try:
                os.remove(ruta)
            except OSError:
                pass

    encontrado = False
    with ThreadPoolExecutor(max_workers=max_paralelo) as pool:
        futuros = {pool.submit(_procesar_uno, u): u for u in urls}
        for futuro in as_completed(futuros):
            resultado = futuro.result()
            for numero in resultado.get("numeros", []):
                if numero in numeros_vistos:
                    continue
                numeros_vistos.add(numero)
                grupo = next((g for g in ultimos4 if numero.endswith(g)), None)
                entrada = {"numero": numero, "documento": resultado["url"]}
                if grupo:
                    entrada["coincide_con"] = grupo
                    coincidencias.append(entrada)
                    encontrado = True
                else:
                    posibles.append(entrada)
            if encontrado:
                break

    return {
        "encontrado": encontrado,
        "coincidencias": coincidencias,
        "posibles": posibles,
        "documentos_intentados": len(futuros),
    }
