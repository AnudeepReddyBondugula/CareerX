import typer

app = typer.Typer()


@app.command()
def version() -> None:
    """
    Display the application version.
    """
    typer.echo("CareerX v0.1.0")
