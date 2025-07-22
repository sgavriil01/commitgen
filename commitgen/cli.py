#!/usr/bin/env python3
"""
Interactive CLI to auto-generate Git commit messages
using Conventional Commits format via an LLM.
"""
import os
import re
import subprocess
import tempfile

typer_import_error = None
try:
    import typer
except ImportError as e:
    typer_import_error = e
from dotenv import load_dotenv
from openai import OpenAI

# Ensure environment variables are loaded
load_dotenv()

# Initialize CLI app
cli_app = typer.Typer(help="Generate precise Git commit messages via AI")

# Configure OpenAI (Groq) client
api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("GROQ_API_KEY not set in environment.")
client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

# Patterns to skip low-value commits
LOW_VALUE_PATTERNS = [
    re.compile(r"(add|remove) debug", re.IGNORECASE),
    re.compile(r"(print|log)\s+statement", re.IGNORECASE),
    re.compile(r"minor\s+(change|update)", re.IGNORECASE),
]

# Exhaustive few-shot examples illustrating multi-file and edge cases
FEW_SHOT_EXAMPLES = """
Example 1: Simple addition
Diff:
--- a/src/math.py
+++ b/src/math.py
@@ -1,1 +1,2 @@
 def subtract(x, y):
-    return x - y
+    return x - y
+
+def add(x, y):
+    return x + y
Commit Message:
feat(math): add add() helper function

Example 2: Debugging statement
Diff:
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,4 @@
 def login(user, pass):
     # ...
     authenticate(user, pass)
+    print("User authenticated")
Commit Message:
chore(auth): add temporary debug log

Example 3: Refactoring
Diff:
--- a/src/main.py
+++ b/src/main.py
@@ -5,5 +5,5 @@
-    logger.info("Starting app")
+    logger.debug("Starting app")
     run()
Commit Message:
refactor(logging): change log level from info to debug

Example 4: Multi-file change
Diff:
diff --git a/src/cli.py b/src/cli.py
--- a/src/cli.py
+++ b/src/cli.py
@@ -1,3 +1,3 @@
 def run_cli():
-    print("Running CLI tool")
+    # print("Running CLI tool")
     parse_args()
diff --git a/src/api.py b/src/api.py
--- a/src/api.py
+++ b/src/api.py
@@ -10,1 +10,1 @@
-    return {"status": "ok"}
+    return {"status": "live"}
Commit Message:
refactor(cli): comment out debug print
fix(api): correct status response from ok to live
"""


def get_full_staged_diff() -> str:
    """
    Capture the current staged Git diff as a string.
    Returns empty string if no staged changes.
    """
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout if result.returncode == 0 else ""


def is_low_value_commit(title: str) -> bool:
    """
    Check if the suggested commit title matches low-value patterns.
    """
    return any(p.search(title) for p in LOW_VALUE_PATTERNS)

def add(x: int, y: int) -> int:
    """
    Simple addition function for demonstration purposes.
    """
    return x + y

def query_commit_message(diff: str, model: str = "llama3-8b-8192") -> tuple[str, str]:
    """
    Send the diff to the LLM and parse back a title and optional body.
    """
    # Build a precise, hygiene-enforced prompt
    prompt = f"""
You are a meticulous developer crafting Git commit messages in Conventional Commits format.

- Your primary goal is to accurately describe the changes in the provided diff.
- Use the format: <type>(<scope>): <summary>
- The scope should be the name of the file or module most affected (e.g., "auth", "api", "cli").
- For changes spanning multiple files, you may provide multiple commit lines.
- Use "feat" for new features, "fix" for bug fixes, "refactor" for code changes that neither fix a bug nor add a feature, and "chore" for routine tasks.
- Focus ONLY on the changes presented in the diff. Do not invent or generalize.

{FEW_SHOT_EXAMPLES}

Now, write the commit message for the following diff:
{diff}
"""

    # Debug: print prompt to logs
    print("--- LLM Prompt Begin ---")
    print(prompt)
    print("--- LLM Prompt End ---")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Generate clear, accurate Git commit messages."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        max_tokens=300,
    )
    content = response.choices[0].message.content.strip()
    lines = content.split("\n", 1)
    title = lines[0].strip()
    body = lines[1].strip() if len(lines) > 1 else ""
    return title, body


def confirm_commit(title: str, body: str) -> str:
    """
    Display the generated title and body, and ask user to confirm, regenerate, or skip.
    """
    typer.echo("\n🔤 Suggested Commit Title:")
    typer.secho(title, fg=typer.colors.CYAN)
    if body:
        typer.echo("\n📄 Suggested Commit Body:")
        typer.echo(body)
    choice = typer.prompt(
        "\nUse this commit message? (y = yes, r = regenerate, s = skip)",
        default="y",
    )
    return choice.lower()


def make_commit(title: str, body: str) -> None:
    """
    Write the title and body to a tempfile and invoke 'git commit'.
    """
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
        if body:
            f.write(f"{title}\n\n{body}")
        else:
            f.write(title)
        f.flush()
        subprocess.run(["git", "commit", "-F", f.name])


@cli_app.command()
def generate():
    """
    Main command: generate and optionally apply a commit message.
    """
    diff = get_full_staged_diff()
    if not diff.strip():
        typer.secho("⚠️ No staged changes detected.", fg=typer.colors.RED)
        raise typer.Exit()

    for _ in range(3):
        title, body = query_commit_message(diff)
        if is_low_value_commit(title):
            typer.secho("⏭️ Detected low-value commit. Skipping.", fg=typer.colors.YELLOW)
            raise typer.Exit()

        choice = confirm_commit(title, body)
        if choice == "y":
            make_commit(title, body)
            typer.secho("✅ Commit created successfully!", fg=typer.colors.GREEN)
            return
        elif choice == "s":
            typer.secho("❌ Commit skipped.", fg=typer.colors.RED)
            return
        else:
            typer.secho("🔁 Regenerating commit message...", fg=typer.colors.YELLOW)

    typer.secho(
        "⚠️ Maximum retries reached. Aborting commit.", fg=typer.colors.RED
    )


if __name__ == "__main__":
    if typer_import_error:
        raise typer_import_error
    cli_app()