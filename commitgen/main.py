import typer
from commitgen.cli import cli_app

app = typer.Typer()
app.add_typer(cli_app)

if __name__ == "__main__":
    app()
