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
| `test_us02_validacao_produto_ativo.py` | US02 produto inativo recusado em venda nova; histórico preservado |
| `unit/test_product_active_policy.py` | US02 política de domínio de produto ativo/inativo |
| `unit/test_product_selection_service.py` | US02 serviço de seleção usado por compras, vendas e movimentações |

## Falhas conhecidas (não são regressão)

`test_estoque_busca_filtro.py` (15) e `test_estoque_alerta_baixo.py` (7) estão
vermelhos desde antes desta branch: descrevem a US04 (busca, filtros por
status e alerta de estoque baixo), cuja implementação se perdeu num merge —
`EstoquePage` não tem mais `apply_filters` nem `search_input`. Os testes
ficaram. A linha de base da suíte é **22 falhas**, confinadas a esses dois
arquivos.

## Limitação conhecida

Não há Postgres, `psql`, Supabase CLI nem daemon Docker neste ambiente, então
as migrations são validadas **estaticamente** (ordem de execução e coerência
entre colunas declaradas e colunas usadas pelas procedures). Os testes do
`supabase_compiler.py` rodam num diretório temporário e nunca tocam o banco
real nem executam `supabase db push`.
