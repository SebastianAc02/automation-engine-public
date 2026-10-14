import os

from loguru import logger

from config.settings import settings
from src.flujos import directorio, scribd
from src.rues import cliente_rues, db, procesador_llm, telefono
from src.rues.modelos import (
    EmpresaObjetivo,
    ResultadoEmpresa,
    TelefonoFuente,
    match_ultimos4,
    tipo_numero,
)
from src.rues.objetivos import seleccionar_batch

_DIRECTORIOS = [
    ("informacolombia", directorio.buscar_empresa_informacolombia),
    ("portafolio", directorio.buscar_empresa_portafolio),
    ("einforma", directorio.buscar_empresa_einforma),
]

_PRIORIDAD_CARGO = {"gerente": 0, "rep_legal": 1, "rep_legal_suplente": 2, "subgerente": 3}


def _personas_por_prioridad(contactos):
    con_cedula = [c for c in contactos if c.documento]
    return sorted(con_cedula, key=lambda c: _PRIORIDAD_CARGO.get(c.cargo_categoria, 9))


def _numeros_directorio(res: dict):
    # Devuelve (numero, nit_verificado, nit_pagina). Guarda TODO lo que el
    # directorio vio, no solo lo verificado: el encontrado (NIT ok) y, si no
    # encontro, los candidatos que igual traian telefono.
    if res.get("encontrado") and res.get("telefono"):
        return [(res["telefono"], True, res.get("nit"))]
    return [
        (c["telefono"], False, c.get("nit"))
        for c in res.get("candidatos", [])
        if c.get("telefono")
    ]


def _clasificar(fuente: str, numero: str, nit_verificado: bool, nit_pagina, ultimos4) -> TelefonoFuente:
    tipo = tipo_numero(numero)
    md = match_ultimos4(numero, ultimos4)
    return TelefonoFuente(
        fuente=fuente, numero=numero, nit_pagina=nit_pagina, tipo=tipo,
        nit_verificado=nit_verificado, match_dian=md,
        supremamente_confirmado=(tipo == "celular" and md), estado="ok",
    )


def procesar_empresa(empresa: EmpresaObjetivo) -> ResultadoEmpresa:
    resultado = ResultadoEmpresa(id_empresa=empresa.id_empresa)
    nombre = empresa.nombre_legal or empresa.nombre_oficial

    # 1. RUES -> IA: todos los representantes vigentes
    try:
        raw = cliente_rues.obtener_representantes(empresa.id_empresa, settings.rues_url)
        resultado.estado_matricula = raw.get("estado_matricula")
        resultado.contactos = procesador_llm.procesar_representantes(
            raw, settings.anthropic_api_key, settings.modelo_llm
        )
    except cliente_rues.RuesNoEncontrado:
        resultado.rues_error = "no_encontrado_rues"

    # 2. Por persona en prioridad (gerente > rep legal > suplente): DIAN, luego
    #    directorios (una vez), luego scribd. Si ninguna da supremamente
    #    confirmado, se cae a la siguiente persona.
    ultimos4: list[str] = []
    directorios_corridos = False
    for persona in _personas_por_prioridad(resultado.contactos):
        d = telefono.buscar_dian(persona.documento)
        resultado.telefonos.append(d)
        if d.numero:
            ultimos4.append(d.numero)

        if not directorios_corridos:
            for fuente, funcion in _DIRECTORIOS:
                try:
                    res = funcion(nombre, empresa.id_empresa, headless=True)
                except Exception as error:
                    logger.warning(f"{empresa.id_empresa} {fuente} fallo: {error}")
                    continue
                for numero, nit_ver, nit_pag in _numeros_directorio(res):
                    resultado.telefonos.append(_clasificar(fuente, numero, nit_ver, nit_pag, ultimos4))
            directorios_corridos = True

        if d.numero and not os.environ.get("RUES_SKIP_SCRIBD"):
            try:
                s = scribd.buscar_telefono_scribd(nombre, [d.numero], headless=True)
                for m in s.get("coincidencias", []):
                    resultado.telefonos.append(
                        TelefonoFuente(
                            fuente="scribd", numero=m["numero"], tipo="celular",
                            match_dian=True, supremamente_confirmado=True, estado="ok",
                        )
                    )
            except Exception as error:
                logger.warning(f"{empresa.id_empresa} scribd fallo: {error}")

        if any(t.supremamente_confirmado for t in resultado.telefonos):
            break

    return resultado


def correr_batch(limite: int) -> list[ResultadoEmpresa]:
    con = db.conectar(settings.engine_db_path)
    salida: list[ResultadoEmpresa] = []
    procesadas = {
        fila[0]
        for fila in con.execute("SELECT id_empresa FROM empresa_objetivo WHERE procesada=1")
    }
    for empresa in seleccionar_batch(settings.prod_db_path, limite, excluidos=procesadas):
        db.guardar_objetivo(con, empresa)
        resultado = procesar_empresa(empresa)
        for contacto in resultado.contactos:
            db.guardar_contacto(con, empresa.id_empresa, contacto)
        for tel in resultado.telefonos:
            db.guardar_telefono(con, empresa.id_empresa, tel)
        db.marcar_procesada(con, empresa.id_empresa, resultado.rues_error)
        sup = [t for t in resultado.telefonos if t.supremamente_confirmado]
        logger.info(
            f"{empresa.id_empresa}: {len(resultado.contactos)}c, "
            f"{len(sup)} supremamente confirmados, "
            f"fuentes={[t.fuente for t in sup]}"
        )
        salida.append(resultado)
    con.close()
    return salida
