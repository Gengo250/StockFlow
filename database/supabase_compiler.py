import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timedelta


def migration_func(orig_dir: str, dest_dir: str, migr_dir: str):
    origin = Path(orig_dir)
    destiny = Path(dest_dir)
    migration = Path(migr_dir)

    files = sorted(origin.rglob("*.sql"))
    if not files:
        print("No files found")
        return

    migration.mkdir(parents=True, exist_ok=True)

    processed_files = []
    time_base = datetime.now()

    print(f"Preparing {len(files)} files for migration")

    for index, original_file in enumerate(files):
        timestamp = (time_base + timedelta(seconds=index)).strftime("%Y%m%d%H%M%S")
        migration_name = f"{timestamp}_{original_file.name}"
        migration_path = migration / migration_name

        shutil.copy2(original_file, migration_path)

        processed_files.append(
            {"original": original_file, "generated_migration": migration_path}
        )

        print(f" -> created: {migration_name}")

    print("Executing supabase db push")

    try:
        result = subprocess.run(
            ["supabase", "db", "push"], check=True, capture_output=True, text=True
        )

        print("Push to supabase done")
        print("Archiving the original files...")

        for item in processed_files:
            file_org = item["original"]

            rel_path = file_org.relative_to(origin)

            final_path = destiny / rel_path

            final_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(file_org), str(final_path))

        print("Archiving done")

    except subprocess.CalledProcessError as error:
        print("The command supabase db push failed")
        print("Details:")
        print(error.stderr)

        print("Undoing local migrations")
        for item in processed_files:
            if item["generated_migration"].exists():
                item["generated_migration"].unlink()

        print("Rollback done")

    except FileNotFoundError:
        print("The command supabase wasnt found")
        print("Check if supabase CLI is installed on your machine")


if __name__ == "__main__":
    ORIGIN_DIR = "./code"
    FINAL_DIR = "./archive/"
    MIG_DIR = "./supabase/migrations/"

    Path(ORIGIN_DIR).mkdir(parents=True, exist_ok=True)

    migration_func(ORIGIN_DIR, FINAL_DIR, MIG_DIR)
