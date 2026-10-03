import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))


def load_env(path="../.env"):
    """Load KEY=VALUE pairs from a .env file into os.environ."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()

# --- Configuration ---
SOURCE_DIR = "code"  # where you write your SQL
SCHEMAS_DIR = os.path.join("supabase", "schemas")
MIGRATIONS_DIR = os.path.join("supabase", "migrations")
CONFIG_FILE = os.path.join("supabase", "config.toml")
PROJECT_REF_FILE = os.path.join("supabase", ".temp", "project-ref")

EXPECTED_PROJECT_REF = os.getenv("SUPABASE_PROJECT_REF")
EXECUTION_ORDER = ["tables", "views", "procedures", "triggers", "policies"]

DESTRUCTIVE = re.compile(r"\bdrop\s+(table|column|schema|type)\b", re.IGNORECASE)

CONFIG_SNIPPET = """[db.migrations]
schema_paths = [
  "./schemas/tables/*.sql",
  "./schemas/views/*.sql",
  "./schemas/procedures/*.sql",
  "./schemas/triggers/*.sql",
  "./schemas/policies/*.sql",
]"""


def fail(message):
    """Print an error message and exit with a non-zero status."""
    print(f"❌ {message}")
    sys.exit(1)


def run(command):
    """Run a command and raise CalledProcessError if it fails."""
    return subprocess.run(command, check=True)


def check_prerequisites():
    """Make sure the environment is ready before generating a migration."""
    if shutil.which("supabase") is None:
        fail("Supabase CLI not found.")

    if shutil.which("docker") is None:
        fail("Docker not found (required by 'supabase db diff').")

    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        fail("Docker is not running (required by 'supabase db diff').")

    if not os.path.exists(CONFIG_FILE):
        fail("supabase/config.toml not found. Run 'supabase init' in this folder.")

    with open(CONFIG_FILE, encoding="utf-8") as f:
        if "schema_paths" not in f.read():
            fail(
                "'schema_paths' is missing from supabase/config.toml. Add this:\n\n"
                + CONFIG_SNIPPET
            )

    if not os.path.exists(PROJECT_REF_FILE):
        fail(
            "Project is not linked. Run: "
            f"supabase link --project-ref {EXPECTED_PROJECT_REF}"
        )

    with open(PROJECT_REF_FILE, encoding="utf-8") as f:
        linked_ref = f.read().strip()

    if linked_ref != EXPECTED_PROJECT_REF:
        fail(
            f"Linked project is {linked_ref}, but {EXPECTED_PROJECT_REF} was expected."
        )


def sync_schemas():
    """Mirror code/ into supabase/schemas/ (files you deleted are removed too)."""
    shutil.rmtree(SCHEMAS_DIR, ignore_errors=True)
    total = 0

    for folder in EXECUTION_ORDER:
        destination = os.path.join(SCHEMAS_DIR, folder)
        os.makedirs(destination, exist_ok=True)

        for path in sorted(glob.glob(os.path.join(SOURCE_DIR, folder, "*.sql"))):
            shutil.copy2(path, destination)
            total += 1

    print(f"📂 {total} file(s) synced to {SCHEMAS_DIR}")


def list_migrations():
    """Return the set of migration files currently on disk."""
    return set(glob.glob(os.path.join(MIGRATIONS_DIR, "*.sql")))


def main():
    parser = argparse.ArgumentParser(
        description="Generate Supabase migrations from the code/ folder"
    )
    parser.add_argument("name", help="migration name, e.g. add_stock_to_products")
    parser.add_argument(
        "-y", "--yes", action="store_true", help="push without asking for confirmation"
    )
    args = parser.parse_args()

    check_prerequisites()
    sync_schemas()

    migrations_before = list_migrations()

    print("\n🔍 Calculating differences (supabase db diff)...")
    try:
        run(
            [
                "supabase",
                "db",
                "schema",
                "declarative",
                "sync",
                "--name",
                args.name,
                "--no-apply",
            ]
        )
    except subprocess.CalledProcessError:
        fail(
            "'db diff' failed. Check the error above "
            "(usually invalid SQL or a dependency ordering issue)."
        )

    new_files = sorted(list_migrations() - migrations_before)
    if not new_files:
        print("✅ No differences. The database already matches your code.")
        return

    for path in new_files:
        print(f"\n📄 Generated: {path}")
        print("-" * 50)
        with open(path, encoding="utf-8") as f:
            print(f.read())
        print("-" * 50)

    if not args.yes:
        answer = input("Apply to Supabase? [y/N] ").strip().lower()
        if answer != "y":
            print("⏸️  Migration kept locally, nothing was applied.")
            print("   Edit or delete the file if needed, then run 'supabase db push'.")
            return

    print("\n🚀 Applying (supabase db push)...")
    try:
        run(["supabase", "db", "push"])
        print("✅ Migration applied!")
    except subprocess.CalledProcessError:
        fail(
            "Push failed. The migration is still in supabase/migrations/ so you can fix it."
        )


if __name__ == "__main__":
    main()
