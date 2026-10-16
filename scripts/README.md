# scripts

Scripts auxiliares de apoio ao desenvolvimento e à manutenção do projeto.

Equipe responsável: Backend

Verificação de vendas em PostgreSQL local (requer `pgcrypto`):

```bash
export STOCKFLOW_TEST_DSN='host=127.0.0.1 port=55439 dbname=postgres user=postgres'
uv run python scripts/verify_postgres.py
uv run python scripts/verify_postgres.py --schema
uv run python scripts/verify_sales.py
```

Os scripts criam/removem apenas bancos próprios `stockflow_verify_*`, recusam
hosts remotos e não acessam Supabase. `verify_sales.py` cobre os modelos
históricos de vendas, checkout pelos widgets, isolamento e concorrência.

Evidências e instruções de aplicação:
[correção de vendas](../docs/auditoria/2026-10-14/README.md).
