import os
import glob
import subprocess
import shutil
from datetime import datetime, timedelta

SOURCE_DIR = "archive"
ARCHIVE_DIR = "archive"
MIGRATIONS_DIR = "supabase/migrations"

EXECUTION_ORDER = ["tables", "views", "procedures", "triggers", "policies"]


def setup_directories():
    """Create the base directories and all subfolders."""
    os.makedirs(MIGRATIONS_DIR, exist_ok=True)
    for folder in EXECUTION_ORDER:
        os.makedirs(os.path.join(SOURCE_DIR, folder), exist_ok=True)
        os.makedirs(os.path.join(ARCHIVE_DIR, folder), exist_ok=True)


def get_sql_files_in_order():
    """Retrieve all .sql files respecting the strict folder order."""
    ordered_files = []
    for folder in EXECUTION_ORDER:
        folder_path = os.path.join(SOURCE_DIR, folder)
        files = sorted(glob.glob(os.path.join(folder_path, "*.sql")))
        ordered_files.extend(files)
    return ordered_files


def process_and_create_migrations(sql_files):
    """Read each file, generate an ordered timestamp, and save as a separate migration."""
    base_time = datetime.now()

    for index, file_path in enumerate(sql_files):
        folder_name = os.path.basename(os.path.dirname(file_path))
        file_name = os.path.splitext(os.path.basename(file_path))[0]

        current_time = base_time + timedelta(seconds=index)
        timestamp_str = current_time.strftime("%Y%m%d%H%M%S")

        migration_filename = f"{timestamp_str}_{folder_name}_{file_name}.sql"
        migration_filepath = os.path.join(MIGRATIONS_DIR, migration_filename)

        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        with open(migration_filepath, "w", encoding="utf-8") as dest:
            dest.write("-- ==========================================\n")
            dest.write(f"-- SOURCE: {folder_name}/{file_name}.sql\n")
            dest.write("-- ==========================================\n\n")
            dest.write(content)

        print(f"📄 Created: {migration_filename}")


def archive_files(sql_files):
    """Move compiled files to the archive."""
    for file_path in sql_files:
        relative_path = os.path.relpath(file_path, SOURCE_DIR)
        destination = os.path.join(ARCHIVE_DIR, relative_path)

        if os.path.abspath(file_path) == os.path.abspath(destination):
            continue

        os.makedirs(os.path.dirname(destination), exist_ok=True)

        if os.path.exists(destination):
            os.remove(destination)

        shutil.move(file_path, destination)


def push_to_supabase():
    """Execute the Supabase push command."""
    print("\n🚀 Pushing to Supabase Cloud...")
    try:
        subprocess.run(["supabase", "db", "push"], check=True)
        print("✅ Successfully pushed to Supabase!")
    except subprocess.CalledProcessError:
        print("❌ Error pushing to Supabase. Check the terminal logs.")
    except FileNotFoundError:
        print("❌ Error: Supabase CLI not found.")


def main():
    print("Starting Advanced Supabase Compiler (Individual Files)...")

    setup_directories()
    sql_files = get_sql_files_in_order()

    if not sql_files:
        print(f"⚠️ No SQL files found in '{SOURCE_DIR}' subfolders. Exiting.")
        return

    print(f"📦 Found {len(sql_files)} SQL file(s). Generating migrations...\n")

    process_and_create_migrations(sql_files)

    archive_files(sql_files)
    print("\n📁 Archived raw SQL files into their respective subfolders.")

    push_to_supabase()


if __name__ == "__main__":
    main()
