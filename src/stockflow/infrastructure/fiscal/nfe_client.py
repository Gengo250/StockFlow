"""Cliente para execução do NFePHP sob demanda via CLI."""

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("stockflow.fiscal")

# Caminho para o script PHP dentro do projeto
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
PHP_SCRIPT_PATH = BASE_DIR / "services_fiscal_php" / "cli_emitir.php"


class NFeClient:
    def __init__(self, script_path: Path = PHP_SCRIPT_PATH):
        self.script_path = script_path

    def emitir_nota(self, tipo_operacao: str, dados_operacao: dict) -> dict:
        """Executa o script PHP apenas no momento da emissão e encerra o processo."""
        payload = {"tipo_operacao": tipo_operacao, **dados_operacao}

        try:
            # Chama o comando: php cli_emitir.php passando o JSON via stdin
            process = subprocess.run(
                ["php", str(self.script_path)],
                input=json.dumps(payload),
                text=True,
                capture_output=True,
                check=False,
            )

            if process.returncode != 0:
                logger.error("Erro no script PHP CLI: %s", process.stderr)
                return {
                    "status": "REJEITADA",
                    "erro": process.stderr or "Falha na execução do processo PHP",
                }

            resposta = json.loads(process.stdout)
            logger.info("Nota emitida via CLI: %s", resposta.get("chave_acesso"))
            return resposta

        except FileNotFoundError:
            logger.error(
                "Binário do PHP não encontrado no PATH do sistema operacional."
            )
            return {
                "status": "ERRO_SISTEMA",
                "mensagem": "PHP não instalado ou não encontrado no PATH.",
            }
        except Exception as exc:
            logger.error("Erro inesperado ao executar PHP sob demanda: %s", exc)
            return {"status": "ERRO_INESPERADO", "mensagem": str(exc)}
