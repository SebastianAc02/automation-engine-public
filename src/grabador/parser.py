import ast


def parsear(codigo: str) -> list[dict]:
    arbol = ast.parse(codigo)
    funcion_run = next(
        nodo for nodo in ast.walk(arbol) if isinstance(nodo, ast.FunctionDef) and nodo.name == "run"
    )

    elementos = []

    for linea in funcion_run.body:
        if not isinstance(linea, ast.Expr) or not isinstance(linea.value, ast.Call):
            continue

        cadena = _desenrollar(linea.value)
        if cadena[0] != ("nombre", "page"):
            continue

        paso = _traducir(cadena)
        if paso is None:
            elementos.append({"no_reconocido": True, "codigo": ast.unparse(linea), "linea": linea.lineno})
        else:
            elementos.append(paso)

    return elementos


def selector_desde_codigo(codigo: str) -> str | None:
    codigo = codigo.strip()
    if not codigo.startswith("page."):
        codigo = f"page.{codigo}"

    try:
        nodo = ast.parse(codigo, mode="eval").body
    except SyntaxError:
        return None

    cadena = _desenrollar(nodo)
    if cadena[0] != ("nombre", "page") or len(cadena) < 2 or cadena[1][0] != "llamada":
        return None

    selector = _base_selector(cadena[1])
    if selector is None:
        return None

    for elemento in cadena[2:]:
        if elemento[0] != "llamada":
            return None
        selector = _refinar_selector(selector, elemento)
        if selector is None:
            return None

    return selector


def _desenrollar(nodo):
    if isinstance(nodo, ast.Name):
        return [("nombre", nodo.id)]
    if isinstance(nodo, ast.Attribute):
        return _desenrollar(nodo.value) + [("attr", nodo.attr)]
    if isinstance(nodo, ast.Call) and isinstance(nodo.func, ast.Attribute):
        return _desenrollar(nodo.func.value) + [("llamada", nodo.func.attr, nodo.args, nodo.keywords)]
    return [("desconocido", nodo)]


def _valor(nodo):
    if isinstance(nodo, ast.Constant):
        return nodo.value
    return ast.unparse(nodo)


def _buscar_kw(keywords, nombre):
    for kw in keywords:
        if kw.arg == nombre:
            return kw.value
    return None


def _base_selector(elemento):
    metodo, args, keywords = elemento[1], elemento[2], elemento[3]

    if metodo == "get_by_role":
        rol = _valor(args[0])
        nombre_kw = _buscar_kw(keywords, "name")
        if nombre_kw is not None:
            return f'role={rol}[name="{_valor(nombre_kw)}"]'
        return f"role={rol}"
    if metodo == "get_by_text":
        return f'text="{_valor(args[0])}"'
    if metodo == "get_by_placeholder":
        return f'[placeholder="{_valor(args[0])}"]'
    if metodo == "locator":
        return _valor(args[0])
    return None


def _refinar_selector(selector, elemento):
    metodo, args, keywords = elemento[1], elemento[2], elemento[3]

    if metodo == "filter":
        has_text = _buscar_kw(keywords, "has_text")
        if has_text is None or selector.startswith(("role=", "text=")):
            return None
        return f'{selector}:has-text("{_valor(has_text)}")'
    if metodo == "nth":
        n = _valor(args[0])
        return f"{selector} >> nth={n}"
    return None


def _traducir(cadena):
    ultimo = cadena[-1]
    if ultimo[0] != "llamada":
        return None
    accion_final, args_final = ultimo[1], ultimo[2]

    if accion_final == "goto":
        return {"accion": "navegar", "url": _valor(args_final[0])}

    eslabones = cadena[1:-1]
    if not eslabones or eslabones[0][0] != "llamada":
        return None

    selector = _base_selector(eslabones[0])
    if selector is None:
        return None

    for elemento in eslabones[1:]:
        if elemento[0] != "llamada":
            return None
        selector = _refinar_selector(selector, elemento)
        if selector is None:
            return None

    if accion_final == "click":
        return {"accion": "clic", "selector": selector}
    if accion_final == "dblclick":
        return {"accion": "extraer", "selector": selector, "patron": None}
    if accion_final == "fill":
        return {"accion": "rellenar", "selector": selector, "valor": _valor(args_final[0])}
    if accion_final == "press":
        return {"accion": "presionar", "selector": selector, "valor": _valor(args_final[0])}

    return None
