import subprocess
import typer
import os
from dotenv import load_dotenv
from openai import OpenAI

cli_app = typer.Typer()

# Load your .env file to get the API key
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1",
)

def query_groq(prompt: str, model: str = "llama3-8b-8192") -> str:
    """Send prompt to Groq and return the response."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are an AI assistant that writes short, clean Git commit messages in Conventional Commits format."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=150,
    )
    return response.choices[0].message.content.strip()

def get_git_diff() -> str:
    """Return the staged git diff with fallback decoding."""
    result = subprocess.run(
        ["git", "diff", "--cached"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    try:
        return result.stdout.decode("utf-8").strip()
    except UnicodeDecodeError:
        return result.stdout.decode("utf-8", errors="replace").strip()

def extract_first_line(message: str) -> str:
    """Return the first non-empty line from a message."""
    for line in message.strip().splitlines():
        if line.strip() and not line.strip().startswith("```"):
            return line.strip()
    return "chore: update"  # fallback

@cli_app.command()
def generate(
    commit: bool = typer.Option(True, help="Immediately commit with the generated message."),
    verbose: bool = typer.Option(False, help="Print the full LLM response.")
):
    """Generate and optionally commit a message from staged code."""
    diff = get_git_diff()
    if not diff:
        typer.echo("⚠️ No staged changes found. Use `git add` first.")
        raise typer.Exit()

    prompt = f"""Write a short, clear Git commit message for the following staged diff.
Use the Conventional Commits format: <type>(<scope>): <description>
Allowed types: feat, fix, chore, docs, refactor, style, test

Diff:
{diff}
"""

    typer.secho("🧠 Prompt sent to Groq", fg=typer.colors.BLUE)
    message_raw = query_groq(prompt)
    message_clean = extract_first_line(message_raw)

    if verbose:
        typer.echo("\n🧾 Full LLM response:\n")
        typer.echo(message_raw)

    typer.secho("\n✅ Final Commit Message:\n", fg=typer.colors.GREEN)
    typer.echo(message_clean)

    if commit:
        result = subprocess.run(["git", "commit", "-m", message_clean])
        if result.returncode == 0:
            typer.secho("✅ Commit created successfully.", fg=typer.colors.GREEN)
        else:
            typer.secho("❌ Commit failed.", fg=typer.colors.RED)

if __name__ == "__main__":
    cli_app()
