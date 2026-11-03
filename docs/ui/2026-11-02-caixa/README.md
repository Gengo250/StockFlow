# Caixa no aplicativo — 02/11/2026

Em **Vendas → Caixa · iniciar / fechar**, administradores e vendedores podem:

1. Informar o saldo inicial/troco e clicar **Iniciar caixa**.
2. Registrar vendas vinculadas à sessão aberta.
3. Voltar ao botão Caixa, contar os valores por forma de pagamento (dinheiro inclui o saldo inicial), informar justificativa se houver diferença e clicar **Fechar caixa**.

A consulta recupera o caixa aberto do operador autenticado. Os campos permanecem preenchidos se houver erro. O botão Atualizar permite consultar novamente após falha de conexão. Fechar o formulário não fecha o caixa. No modo demo, tudo permanece somente em memória.

## Banco Supabase

A interface depende da migration `database/supabase/migrations/20261102180000_register_app_flow.sql`, posterior à migration US23. **Não aplicada ao Supabase nesta sessão.** Revisar/aplicar pelo fluxo de migrations do projeto antes de usar a função no backend remoto, depois reiniciar o aplicativo.

A migration resolve automaticamente a sessão nas vendas, restringe as RPCs ao operador autenticado ADMIN/SELLER e garante exclusividade por índices únicos. Caso já existam sessões OPEN duplicadas, reconciliá-las antes de aplicar; a migration recusa a inconsistência sem fechar registros arbitrariamente. Não altera vendas antigas nem abre/fecha caixas reais durante instalação.

O terminal é criado automaticamente na primeira abertura e reutilizado nas seguintes. A interface não implementa histórico de caixa, sangria ou suprimento.

## Evidências

- `vendas.png`: localização do botão no app.
- `abrir.png` e `fechar.png`: diálogos capturados em Qt offscreen/Fusion.
- Testes: `tests/test_cash_register_app.py`, `tests/test_cash_register_dialog.py`, `tests/integration/test_cash_register_ui_flow.py`.
- Banco local descartável, schema declarativo e cadeia de migrations testados separadamente.
- Revisão independente encontrou troca de sessão entre consulta e fechamento; corrigida passando o ID exibido até a RPC, com teste de regressão.

Avaliação na janela nativa e aplicação da migration remota permanecem pendentes. Sem commit ou push.

Para repetir a suíte com configurações Qt isoladas por processo, sem adicionar dependências ao projeto:

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
PYTHONPATH=docs/ui/2026-11-02-caixa \
uv run --frozen --with pytest-xdist pytest tests/ -q -n 4 --dist loadfile -p isolated_settings
```

A primeira execução serial não produziu resumo final. Nela, testes antigos de venda/devolução precisaram passar a abrir caixa na preparação; os 32 testes afetados e de carregamento passaram após o ajuste. Um teste de responsividade excedeu seu prazo na execução longa e passou isoladamente. O resultado conclusivo da execução completa em processos isolados está em `pytest-final.log`.

Resultado final: **1593 passed, 53 skipped**, sem falhas, em 275,36 s (suíte completa com quatro processos e configurações isoladas); **52 passed** na integração PostgreSQL local; **127 passed** na seleção de caixa/contratos e **32 passed** nas regressões de venda/devolução/carregamento. Os skips da suíte geral incluem integração sem DSN; ela foi executada separadamente no PostgreSQL descartável.
