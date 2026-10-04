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
| `test_estoque_busca_filtro.py` | US03 consulta de saldo/mínimo/situação, busca e ativar/desativar |
| `test_estoque_alerta_baixo.py` | US04 um teste por critério de conclusão do cartão |
| `test_movimentacoes_estoque.py` | US03 saldo derivado das movimentações confirmadas (estático) |
| `unit/test_supabase_product_repository.py` | adaptador de catálogo no Supabase, contra cliente falso |
| `unit/test_supabase_auth.py` | login pelo Supabase Auth e montagem da sessão |
| `unit/test_backend_selection.py` | escolha entre demonstração e banco por `STOCKFLOW_BACKEND` |
| `unit/test_user_directory.py` | tradução da linha de usuário e leitura por `fn_list_company_users` |
| `test_usuarios_do_banco.py` | tela de Usuários trocando demonstração por dados da empresa |

## Linha de base

**A suíte passa inteira.** Qualquer vermelho é regressão.

Histórico, para quem encontrar a referência antiga: até a recuperação da US04
a linha de base eram **22 falhas** em `test_estoque_busca_filtro.py` (15) e
`test_estoque_alerta_baixo.py` (7). A implementação da história tinha se
perdido num merge e só os testes sobreviveram. Ela voltou em
`presentation/pages/estoque.py` (busca, filtros, `apply_filters`,
`toggle_product_status`) e `domain/stock_level.py` (cálculo do status).

## Limitação conhecida

Não há Postgres, `psql`, Supabase CLI nem daemon Docker neste ambiente, então
as migrations são validadas **estaticamente** (ordem de execução e coerência
entre colunas declaradas e colunas usadas pelas procedures). Os testes do
`supabase_compiler.py` rodam num diretório temporário e nunca tocam o banco
real nem executam `supabase db push`.
