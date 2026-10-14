import subprocess
import tempfile
from pathlib import Path


def grabar(url: str) -> str:
    with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as temporal:
        ruta_temp = Path(temporal.name)

    subprocess.run(
        ["playwright", "codegen", url, "-o", str(ruta_temp), "--target", "python"],
        check=True,
    )

    return ruta_temp.read_text()
