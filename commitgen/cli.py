import subprocess
import typer
import os
from dotenv import load_dotenv
from openai import OpenAI
import re
import tempfile
import sys

cli_app = typer.Typer()
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

def query_commit_message(diff: str, model="llama3-8b-8192") -> tuple[str, str]:
    prompt = f"""
You are an experienced developer writing Git commit messages using the Conventional Commits format.

- Use the format: <type>(<scope>): <short summary>
- Follow up with a longer description if needed (separated by a newline).
- Do not include explanations or markdown.
- Types: feat, fix, chore, docs, refactor, style, test

Diff:
{diff}
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Write clear, concise Git commit messages based on diffs."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4,
        max_tokens=300,
    )
    content = response.choices[0].message.content.strip()
    parts = content.split("\n", 1)
    title = parts[0].strip()
    body = parts[1].strip() if len(parts) > 1 else ""
    return title, body

def get_staged_diff_by_file() -> dict[str, str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--unified=0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.stdout is None:
        return {}

    try:
        output = result.stdout.decode("utf-8")
    except UnicodeDecodeError:
        output = result.stdout.decode("utf-8", errors="replace")

    current_file = None
    files = {}
    lines = []

    for line in output.splitlines():
        if line.startswith("diff --git"):
            if current_file and lines:
                files[current_file] = "\n".join(lines)
            lines = [line]
            parts = line.split(" ")
            current_file = parts[2].replace("a/", "", 1)
        elif current_file:
            lines.append(line)

    if current_file and lines:
        files[current_file] = "\n".join(lines)

    return files

def confirm_commit(title: str, body: str) -> bool:
    typer.echo(f"\n📝 Commit Title:\n{title}")
    if body:
        typer.echo(f"\n📄 Commit Body:\n{body}")

    choice = typer.prompt("\nProceed with this commit? (y = yes, n = no)", default="y")
    return choice.lower() == "y"

def make_commit(title: str, body: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w+", delete=False, encoding="utf-8") as f:
        f.write(title + "\n\n" + body if body else title)
        f.flush()
        subprocess.run(["git", "commit", "-F", f.name])

@cli_app.command()
def generate():
    files = get_staged_diff_by_file()
    if not files:
        typer.secho("⚠️ No staged changes found.", fg=typer.colors.RED)
        raise typer.Exit()

    squash = typer.confirm(f"{len(files)} file(s) changed. Do you want to squash into a single commit?", default=True)

    if squash:
        combined_diff = "\n\n".join(files.values())
        title, body = query_commit_message(combined_diff)
        if confirm_commit(title, body):
            make_commit(title, body)
            typer.secho("✅ Commit created.", fg=typer.colors.GREEN)
    else:
        for file, diff in files.items():
            typer.echo(f"\n🔍 Processing: {file}")
            title, body = query_commit_message(diff)
            if confirm_commit(title, body):
                subprocess.run(["git", "add", file])
                make_commit(title, body)
                typer.secho(f"✅ Committed {file}", fg=typer.colors.GREEN)

if __name__ == "__main__":
    cli_app()
