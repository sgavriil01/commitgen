import subprocess
import os
import re
import typer
from typing import List
from dotenv import load_dotenv
from openai import OpenAI

cli_app = typer.Typer()

# Load GROQ_API_KEY
load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("Missing GROQ_API_KEY in .env")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1",
)

# Prompt instructions with few-shot examples
FEW_SHOT_PROMPT = """
You are an expert software engineer writing Git commit messages in Conventional Commits format.
Use this format: <type>(<scope>): <description>
Do not include explanations. Only return a single commit message line.
Allowed types: feat, fix, chore, docs, refactor, style, test

Examples:
Diff:
diff --git a/utils/math.py b/utils/math.py
+def square(x):
+    return x * x

Commit:
feat(utils): add square function

Diff:
diff --git a/api/main.py b/api/main.py
-import logging
+import logging
+logging.basicConfig(level=logging.DEBUG)

Commit:
chore(api): add debug logging setup
"""

def run_git_command(args: List[str]) -> str:
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.stdout.decode("utf-8", errors="replace").strip()

def get_staged_files() -> List[str]:
    output = run_git_command(["git", "diff", "--cached", "--name-only"])
    return output.splitlines()

def get_file_diff(filepath: str) -> str:
    return run_git_command(["git", "diff", "--cached", "--unified=0", "--", filepath])

def query_groq(diff: str) -> str:
    full_prompt = f"{FEW_SHOT_PROMPT}\n\nDiff:\n{diff}\n\nCommit:"
    response = client.chat.completions.create(
        model="llama3-8b-8192",
        messages=[
            {"role": "system", "content": "You're a clean Git commit message writer."},
            {"role": "user", "content": full_prompt}
        ],
        temperature=0.4,
        max_tokens=100
    )
    return response.choices[0].message.content.strip()

@cli_app.command()
def generate(mode: str = typer.Option("squash", help="Mode: 'squash' or 'split'")):
    """Generate Git commit messages using Groq based on staged changes."""
    files = get_staged_files()
    if not files:
        typer.secho("⚠️ No staged changes found. Use `git add` first.", fg=typer.colors.YELLOW)
        raise typer.Exit()

    if mode == "split":
        for file in files:
            diff = get_file_diff(file)
            typer.secho(f"\n📄 {file}", fg=typer.colors.CYAN)
            commit_msg = query_groq(diff)
            typer.echo(f"✅ Suggested: {commit_msg}")
            choice = typer.prompt("Commit this? (y = yes, s = skip)", default="y").lower()
            if choice == "y":
                subprocess.run(["git", "commit", "-m", commit_msg, "--", file])
                typer.secho("✅ Committed.\n", fg=typer.colors.GREEN)
            else:
                typer.secho("⏩ Skipped.\n", fg=typer.colors.YELLOW)

    else:  # squash mode
        full_diff = run_git_command(["git", "diff", "--cached", "--unified=0"])
        commit_msg = query_groq(full_diff)
        typer.echo(f"\n✅ Suggested Commit Message:\n{commit_msg}")
        confirm = typer.prompt("Do you want to commit with this message? (y/n)", default="y").lower()
        if confirm == "y":
            subprocess.run(["git", "commit", "-m", commit_msg])
            typer.secho("✅ Commit created.", fg=typer.colors.GREEN)
        else:
            typer.secho("❌ Commit cancelled.", fg=typer.colors.RED)

if __name__ == "__main__":
    cli_app()
    print("Dbugging: CLI app initialized with Groq API key.")
