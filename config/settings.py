from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

RAIZ = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    trawl_url: str = ""
    timeout_default: float = 30.0
    log_level: str = "INFO"
    dir_recetas: Path = RAIZ / "recetas"
    dir_resultados: Path = RAIZ / "resultados"
    dir_logs: Path = RAIZ / "logs"
    rues_url: str = "https://rues-scrapper.onrender.com"
    anthropic_api_key: str = ""
    modelo_llm: str = "claude-sonnet-5"
    prod_db_path: str = "/data/isps.db"
    engine_db_path: str = str(RAIZ / "rues_engine.db")
    # dian corre con cedula, motor camoufox; lee los ultimos 4 digitos del
    # celular enmascarado en el portal publico de la DIAN, sin disparar SMS.
    dian_activo: bool = True
    # proxy SOCKS para el navegador (camoufox). Usado para que el computo viva
    # en el VPS pero el trafico egrese por una IP residencial via tunel SSH
    # inverso (socks5://127.0.0.1:1080). Vacio = sin proxy, sale directo.
    camoufox_proxy: str = ""
    # servicio de resolucion de captchas (2captcha.com). Vacio = deshabilitado,
    # los flujos que detecten un captcha simplemente fallan ese intento.
    twocaptcha_api_key: str = ""


settings = Settings()
