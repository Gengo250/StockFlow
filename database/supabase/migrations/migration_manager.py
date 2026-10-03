
import os
import shutil
from pathlib import Path


ARCHIVE_DIR = Path("database/archive")

MIGRATIONS_DIR = Path("supabase/migrations")


EXECUTION_ORDER = [
    "tables", 
    "procedures",   
    "functions",    
    "views",        
    "policies",    
]

def organize_migrations():
    print("🚀 Iniciando a orquestração de migrations...")

    if MIGRATIONS_DIR.exists():
        print(f"🧹 Limpando pasta de migrations antiga: {MIGRATIONS_DIR}")
        shutil.rmtree(MIGRATIONS_DIR)
    MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

    file_count = 0

    # 2. Percorrer a ordem de execução
    for stage in EXECUTION_ORDER:
        stage_path = ARCHIVE_DIR / stage

        if not stage_path.exists():
            print(f"⚠️ Aviso: Pasta {stage_path} não encontrada. Pulando...")
            continue

        print(f"📦 Processando estágio: {stage}")

        files = sorted([f for f in stage_path.glob("*.sql")])

        for i, sql_file in enumerate(files):
            version_prefix = f"20261002{i+1:03d}"
            dest_filename = f"{version_prefix}_{sql_file.name}"
            dest_path = MIGRATIONS_DIR / dest_filename

            shutil.copy2(sql_file, dest_path)
            file_count += 1
            print(f"   ✅ {sql_file.name} -> {dest_filename}")

    print(f"\n✨ Sucesso! {file_count} arquivos foram orquestrados em {MIGRATIONS_DIR}")
    print("\n👉 Agora você pode rodar: npx supabase db push")

if __name__ == "__main__":
    try:
        organize_migrations()
    except Exception as e:
        print(f"❌ Erro durante a orquestração: {e}")
