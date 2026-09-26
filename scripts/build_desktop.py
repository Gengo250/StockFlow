"""Gera o executavel desktop do StockFlow.

Uso:

    uv run python scripts/build_desktop.py              # build + smoke test
    uv run python scripts/build_desktop.py --no-smoke   # so o build
    uv run python scripts/build_desktop.py --keep-build # nao limpa build/

O mesmo comando funciona em Linux e Windows: a receita fica em
packaging/stockflow.spec.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SPEC = PROJECT_ROOT / "packaging" / "stockflow.spec"

BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"

# Segundos que o executavel precisa sobreviver no smoke test para ser
# considerado saudavel. Falha de import ou dado faltando mata o
# processo bem antes disso.
SMOKE_TIMEOUT = 15


def limpar(manter_build):
    """Remove artefatos da build anterior."""

    alvos = [DIST_DIR] if manter_build else [DIST_DIR, BUILD_DIR]

    for alvo in alvos:
        if alvo.exists():
            print(f"  removendo {alvo.relative_to(PROJECT_ROOT)}/")
            shutil.rmtree(alvo)


def compilar():
    """Roda o PyInstaller sobre o .spec."""

    comando = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        str(SPEC),
    ]

    print(f"  {' '.join(comando)}\n")

    resultado = subprocess.run(comando, cwd=PROJECT_ROOT)

    return resultado.returncode


def localizar_executavel():
    """Devolve o executavel recem gerado em dist/."""

    candidatos = [
        caminho
        for caminho in DIST_DIR.iterdir()
        if caminho.is_file() and caminho.name.startswith("StockFlow-")
    ]

    if not candidatos:
        return None

    return max(candidatos, key=lambda caminho: caminho.stat().st_mtime)


def smoke_test(executavel):
    """Sobe o executavel sem tela e confere que ele nao morre.

    Usa QT_QPA_PLATFORM=offscreen para funcionar tambem em CI, onde
    nao existe servidor grafico. Pega justamente o erro que so
    aparece dentro do empacotado e nunca no `uv run`.
    """

    ambiente = dict(os.environ)
    ambiente["QT_QPA_PLATFORM"] = "offscreen"

    processo = subprocess.Popen(
        [str(executavel)],
        env=ambiente,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        saida, _ = processo.communicate(timeout=SMOKE_TIMEOUT)

    except subprocess.TimeoutExpired:
        # Sobreviveu ao timeout: e exatamente o que se espera de uma
        # janela aberta esperando eventos.
        processo.terminate()

        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()

        return True, ""

    # Terminou sozinho antes da hora: algo quebrou.
    return False, saida


def formatar_tamanho(bytes_totais):

    return f"{bytes_totais / (1024 * 1024):.1f} MB"


def main():

    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--no-smoke",
        action="store_true",
        help="pula o smoke test do executavel gerado",
    )

    parser.add_argument(
        "--keep-build",
        action="store_true",
        help="mantem build/ para acelerar builds seguintes",
    )

    argumentos = parser.parse_args()

    if not SPEC.exists():
        print(f"ERRO: receita nao encontrada em {SPEC}")
        return 1

    print("\n[1/3] Limpando artefatos anteriores")
    limpar(argumentos.keep_build)

    print("\n[2/3] Compilando com PyInstaller")

    inicio = time.monotonic()

    codigo = compilar()

    duracao = time.monotonic() - inicio

    if codigo != 0:
        print(f"\nERRO: PyInstaller terminou com codigo {codigo}")
        return codigo

    executavel = localizar_executavel()

    if executavel is None:
        print(f"\nERRO: nenhum executavel encontrado em {DIST_DIR}")
        return 1

    print(f"\n  build concluida em {duracao:.0f}s")
    print(f"  arquivo: {executavel}")
    print(f"  tamanho: {formatar_tamanho(executavel.stat().st_size)}")

    if argumentos.no_smoke:
        print("\n[3/3] Smoke test pulado (--no-smoke)")
        return 0

    print(f"\n[3/3] Smoke test ({SMOKE_TIMEOUT}s, modo offscreen)")

    passou, saida = smoke_test(executavel)

    if not passou:
        print("\nFALHOU: o executavel encerrou sozinho. Saida:\n")
        print(saida)
        return 1

    print("\n  OK: executavel sobreviveu ao smoke test")
    print(f"\nPronto. Para rodar:\n\n    {executavel}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
