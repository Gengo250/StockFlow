# Testes

Suíte de verificação das features da branch `persistence-db`.

## Como rodar

```bash
QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q
```

A plataforma `offscreen` deixa os testes de UI rodarem sem servidor gráfico
(útil em CI). Sem ela, o Qt tenta abrir janelas reais.

## O que cada arquivo cobre

| Arquivo | Commit / feature |
|---|---|
| `test_estoque_busca_filtro.py` | `4fab981` busca, filtros e ativar/desativar produto |
| `test_estoque_alerta_baixo.py` | `9357b66` alerta de estoque baixo (US04) e ordenação por criticidade |
| `test_vendas_clientes.py` | `af9fb43` página de vendas e associação de clientes |
| `test_integracao_clientes_vendas.py` | `af9fb43` integração Usuários → Vendas |
| `test_database_migrations.py` | `cc904e5` ordem e coerência das migrations SQL |
| `test_supabase_compiler.py` | `cc904e5` comportamento do `supabase_compiler.py` |

## Limitação conhecida

Não há Postgres, `psql`, Supabase CLI nem daemon Docker neste ambiente, então
as migrations são validadas **estaticamente** (ordem de execução e coerência
entre colunas declaradas e colunas usadas pelas procedures). Os testes do
`supabase_compiler.py` rodam num diretório temporário e nunca tocam o banco
real nem executam `supabase db push`.
