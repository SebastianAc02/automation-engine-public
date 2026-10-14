import typer

from src.rues.runner import correr_batch

app = typer.Typer()


@app.command()
def batch(limite: int = typer.Option(10, "--limite")):
    resultados = correr_batch(limite)
    typer.echo(f"{len(resultados)} empresas procesadas")


if __name__ == "__main__":
    app()
