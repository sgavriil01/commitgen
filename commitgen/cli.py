import subprocess
import requests
import typer

app = typer.Typer()

OLLAMA_MODEL = "mistral"  # Or any model the user has pulled locally

def get_git_diff() -> str:
    """Return the staged git diff."""
    result = subprocess.run(["git", "diff", "--cached"], capture_output=True, text=True)
    return result.stdout.strip()

def query_ollama(prompt: str, model: str = OLLAMA_MODEL) -> str:
    """Send prompt to Ollama and return the response."""
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": model, "prompt": prompt, "stream": False}
    )
    return response.json().get("response", "").strip()

@app.command()
def generate(write: bool = typer.Option(False, help="Write to .git/COMMIT_EDITMSG")):
    """Generate a commit message from staged code."""
    diff = get_git_diff()
    if not diff:
        typer.echo("⚠️ No staged changes found. Use `git add` first.")
        raise typer.Exit()

    # Prompt with Conventional Commit format guidance
    prompt = f"""You are an AI assistant that writes Git commit messages.
Follow this format: <type>(<scope>): <description>
Allowed types: feat, fix, chore, docs, refactor, style, test

Write a commit message for this diff:\n\n{diff}
"""

    message = query_ollama(prompt)

    typer.secho("\n✅ Suggested Commit Message:\n", fg=typer.colors.GREEN)
    typer.echo(message)

    if write:
        try:
            with open(".git/COMMIT_EDITMSG", "w") as f:
                f.write(message + "\n")
            typer.secho("📝 Written to .git/COMMIT_EDITMSG", fg=typer.colors.BLUE)
        except Exception as e:
            typer.secho(f"❌ Failed to write message: {e}", fg=typer.colors.RED)

if __name__ == "__main__":
    app()
