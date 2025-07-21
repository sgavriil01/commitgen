import subprocess
import typer
import os
from dotenv import load_dotenv
from openai import OpenAI
import re

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

def extract_first_valid_commit_line(message: str) -> str:
    """Return the first valid Conventional Commit line, stripped of markdown."""
    pattern = re.compile(r"^(feat|fix|chore|docs|refactor|style|test)(\([\w\-]+\))?: .+")
    for line in message.strip().splitlines():
        clean = re.sub(r"^\*\*(.*?)\*\*$", r"\1", line.strip())  # remove **bold**
        if pattern.match(clean):
            return clean
    return "chore: update"  # fallback

@cli_app.command()
def generate():
    """Interactively generate and confirm a commit message from staged code."""
    diff = get_git_diff()
    if not diff:
        typer.echo("⚠️ No staged changes found. Use `git add` first.")
        raise typer.Exit()

    prompt_template = """Write a Git commit message for the following staged diff.
Use the Conventional Commits format: <type>(<scope>): <description>
Allowed types: feat, fix, chore, docs, refactor, style, test

Diff:
{diff}
"""

    attempt = 0
    max_attempts = 3
    message_clean = None

    while attempt < max_attempts:
        prompt = prompt_template.format(diff=diff)
        typer.secho("🧠 Prompt sent to Groq...", fg=typer.colors.CYAN)
        message_raw = query_groq(prompt)
        message_clean = extract_first_valid_commit_line(message_raw)

        typer.secho("\n✅ Suggested Commit Message:\n", fg=typer.colors.GREEN)
        typer.echo(message_clean)

        choice = typer.prompt(
            "\n🤖 Do you want to commit with this message? (y = yes, r = regenerate, n = cancel)",
            default="y"
        ).lower()

        if choice == "y":
            try:
                result = subprocess.run(["git", "commit", "-m", message_clean])
                if result.returncode == 0:
                    typer.secho("✅ Commit created successfully.", fg=typer.colors.GREEN)
                else:
                    typer.secho("❌ Commit failed.", fg=typer.colors.RED)
            except Exception as e:
                typer.secho(f"❌ Error: {e}", fg=typer.colors.RED)
            break

        elif choice == "r":
            attempt += 1
            typer.secho(f"🔁 Regenerating... ({attempt}/{max_attempts})", fg=typer.colors.YELLOW)
        else:
            typer.secho("❌ Commit cancelled.", fg=typer.colors.RED)
            break

    else:
        typer.secho("⚠️ Max regenerations reached. No commit made.", fg=typer.colors.RED)


if __name__ == "__main__":
    cli_app()
