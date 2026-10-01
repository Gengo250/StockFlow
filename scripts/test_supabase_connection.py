"""Testa a conexão com o Supabase consultando a tabela connection_test.

Executar a partir da raiz do projeto:

    uv run python scripts/test_supabase_connection.py
"""

from stockflow.infrastructure.database.supabase_client import supabase

response = supabase.table("connection_test").select("*").execute()

print(response.data)
