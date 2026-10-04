"""Cliente Supabase compartilhado pela aplicação.

PREGUIÇOSO DE PROPÓSITO. A versão anterior criava o cliente no corpo do
módulo, lendo `os.environ[...]` direto:

    supabase: Client = create_client(os.environ["SUPABASE_URL"], ...)

Isso fazia duas coisas ruins. Primeiro, `KeyError` em tempo de IMPORT quando
não havia `.env` — quem só quisesse importar o pacote (um teste, uma
ferramenta, a própria UI em modo demonstração) não conseguia. Segundo, criava
conexão como efeito colateral de importar, que é o motivo de
`scripts/test_supabase_connection.py` quebrar a coleta do `pytest` ao ser
varrido pelo nome `test_*`.

Aqui o cliente só nasce quando alguém pede, e `is_configured()` permite
decidir entre banco e demonstração sem capturar exceção.
"""

import os

from dotenv import load_dotenv

URL_VAR = "SUPABASE_URL"
KEY_VAR = "SUPABASE_PUBLISHABLE_KEY"

_client = None


def _credenciais():
    # Recarregado a cada consulta: o `.env` pode ser criado depois do import,
    # e `load_dotenv` não sobrescreve variável já exportada no ambiente.
    load_dotenv()
    return os.environ.get(URL_VAR), os.environ.get(KEY_VAR)


def is_configured() -> bool:
    """Diz se há URL e chave para abrir conexão, sem abrir nenhuma."""
    url, key = _credenciais()
    return bool(url and key)


def get_client():
    """Cliente único do processo. Levanta `RuntimeError` se faltar configuração.

    O import de `supabase` fica DENTRO da função: o pacote puxa httpx e
    websockets, e pagar esse custo em todo import de `stockflow` atrasaria a
    abertura da janela mesmo quando a aplicação roda em modo demonstração.
    """
    global _client
    if _client is not None:
        return _client

    url, key = _credenciais()
    if not (url and key):
        raise RuntimeError(
            f"Defina {URL_VAR} e {KEY_VAR} no .env (modelo em .env.example) "
            "para usar o backend de banco."
        )

    from supabase import create_client

    _client = create_client(url, key)
    return _client


def reset_client() -> None:
    """Descarta o cliente em cache.

    Serve para teste e para troca de credencial em runtime. Não encerra
    sessão: quem fez login e quer sair chama `auth.sign_out()` antes.
    """
    global _client
    _client = None


def __getattr__(name):
    """`from ...supabase_client import supabase` continua funcionando.

    O atributo de módulo resolve na primeira leitura, para não quebrar os
    scripts que já importavam `supabase` — mas agora sem conectar durante o
    import do módulo.
    """
    if name == "supabase":
        return get_client()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
