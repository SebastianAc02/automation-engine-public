import httpx


class RuesNoEncontrado(Exception):
    pass


def obtener_representantes(nit: str, base_url: str, timeout: float = 60.0) -> dict:
    url = f"{base_url}/get-representatives/{nit}"
    with httpx.Client(timeout=timeout) as cliente:
        respuesta = cliente.get(url)
        if respuesta.status_code == 404:
            raise RuesNoEncontrado(nit)
        respuesta.raise_for_status()
        return respuesta.json()


def calentar(base_url: str, timeout: float = 60.0) -> bool:
    with httpx.Client(timeout=timeout) as cliente:
        return cliente.get(f"{base_url}/").status_code == 200
