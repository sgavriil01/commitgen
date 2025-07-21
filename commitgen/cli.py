import subprocess
import typer
import os
from dotenv import load_dotenv
from openai import OpenAI
import re
import tempfile

cli_app = typer.Typer()
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")

LOW_VALUE_PATTERNS = [
    re.compile(r"(add|remove) debug", re.IGNORECASE),
    re.compile(r"(print|log)\s+statement", re.IGNORECASE),
    re.compile(r"minor\s+(change|update)", re.IGNORECASE),
]

FEW_SHOT_EXAMPLES = """
Example 1:
Diff:
+ def add(x, y):
+     return x + y
Commit Message:
feat(math): add add() helper function

Example 2:
Diff:
+ print("Debugging auth flow")
Commit Message:
chore(auth): add temporary debug log

Example 3:
Diff:
- logger.info("Start")
+ logger.debug("Start")
Commit Message:
refactor(logging): change log level from info to debug
"""

def query_commit_message(diff: str, model="llama3-8b-8192") -> tuple[str, str]:
    prompt = f"""
You are an experienced developer writing Git commit messages using the Conventional Commits format.

- Format: <type>(<scope>): <summary>
- Add a second line with an optional longer explanation.
- Only output the message. Do not add extra text or formatting.

{FEW_SHOT_EXAMPLES}

Now write the commit message for the following diff:
{diff}
"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Write clear, meaningful Git commit messages."},
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
    result = subprocess.run(["git", "diff", "--cached", "--unified=0"], capture_output=True, text=True, encoding="utf-8")
    if result.returncode != 0 or not result.stdout:
        return {}
    current_file = None
    files = {}
    lines = []

    for line in result.stdout.splitlines():
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

def is_low_value_commit(title: str) -> bool:
    return any(pat.search(title) for pat in LOW_VALUE_PATTERNS)

def confirm_commit(title: str, body: str) -> str:
    typer.echo(f"\n🔤 Commit Title:\n{title}")
    if body:
        typer.echo(f"\n📄 Commit Body:\n{body}")

    choice = typer.prompt("\nDo you want to commit this? (y = yes, r = regenerate, s = skip)", default="y")
    return choice.lower()

def make_commit(title: str, body: str) -> None:
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as f:
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
        for attempt in range(3):
            title, body = query_commit_message(combined_diff)
            if is_low_value_commit(title):
                typer.secho("⏭️ Skipping low-value commit.", fg=typer.colors.YELLOW)
                return
            choice = confirm_commit(title, body)
            if choice == "y":
                make_commit(title, body)
                typer.secho("✅ Commit created.", fg=typer.colors.GREEN)
                return
            elif choice == "s":
                typer.secho("❌ Commit skipped.", fg=typer.colors.RED)
                return
            else:
                typer.secho("🔁 Regenerating...", fg=typer.colors.YELLOW)
        typer.secho("⚠️ Max retries reached. Aborting.", fg=typer.colors.RED)
    else:
        for file, diff in files.items():
            typer.echo(f"\n🔍 Processing: {file}")
            for attempt in range(3):
                title, body = query_commit_message(diff)
                if is_low_value_commit(title):
                    typer.secho("⏭️ Skipping low-value commit.", fg=typer.colors.YELLOW)
                    break
                choice = confirm_commit(title, body)
                if choice == "y":
                    subprocess.run(["git", "add", file])
                    make_commit(title, body)
                    typer.secho(f"✅ Committed {file}", fg=typer.colors.GREEN)
                    break
                elif choice == "s":
                    typer.secho(f"❌ Skipped {file}", fg=typer.colors.RED)
                    break
                else:
                    typer.secho("🔁 Regenerating...", fg=typer.colors.YELLOW)
            else:
                typer.secho(f"⚠️ Max retries for {file}. Skipping.", fg=typer.colors.RED)

if __name__ == "__main__":
    cli_app()
