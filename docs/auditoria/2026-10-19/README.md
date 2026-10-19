# Correções preservadas após atualização da main

Em 19/10/2026, a `main` local avançou de `19b54d7` para `1cef0c4` por
fast-forward. As correções locais foram reaplicadas, com resolução dos
conflitos de `novo_produto.py` e `user_table.py`. O usuário pediu interromper
a ampliação da investigação, organizar o trabalho e publicá-lo na `main`.

## Correções incluídas

- Movimentações: import de `QColor`, busca e situação aplicadas antes da
  paginação, limpeza consistente dos filtros, contagem de resultados e ações
  preservadas. O novo botão de detalhes recebido do remoto fica depois das
  ações existentes; sua conexão à janela continua pendente.
- Vendas: recuperação dos itens, pagamento, desconto e status no histórico
  Supabase; busca nas colunas e itens, preservada na recarga; remoção do método
  duplicado recebido do remoto, que referenciava uma tabela inexistente.
- Usuários: contrato do widget, filtros, identidade das ações após recarga,
  permissões e fonte compartilhada de demonstração preservados na integração.
- Fornecedores: import de `QComboBox` que bloqueava a abertura da janela e
  campo de busca recolocado no layout.
- Produtos: preservação de NCM/EAN na edição, mantendo o novo campo de máximo
  recebido do remoto; gravação dos limites mínimo/máximo numa única transação.
- Interface: páginas roláveis sem ampliar a janela, controles de formulário
  e ícones SVG incluídos no empacotamento.
- SQL: dependências de tabelas corrigidas, ordem de colunas das views
  compatível com atualização, mínimo opcional, máximo efetivo e gravação
  atômica de limites. Espelhos atualizados. A migration H13 foi renomeada de
  `20261014120000_h13_protect_confirmed_movements.sql` para
  `20261018130000_h13_protect_confirmed_movements.sql` para eliminar a versão
  duplicada. Novas migrations: `20261018140000_fix_effective_max_stock.sql`
  e `20261018150000_atomic_product_stock_limits.sql`.
- Testes: fixtures de PostgreSQL local isolado e ajuste dos testes ao
  contrato síncrono de `MovementService.adjust`, com sessão autorizada.

## Verificação concluída

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
  .venv/bin/python -m pytest \
  tests/test_feature_ui.py tests/test_window_viewport.py \
  tests/test_usuarios_do_banco.py tests/test_ui_regression.py \
  tests/test_database_migrations.py tests/test_schema_declarativo.py \
  tests/unit/test_stock_maximum.py \
  tests/unit/test_supabase_product_repository.py -q --tb=short
```

Resultado: **134 passed**, em 9,05 s. Sintaxe dos 201 arquivos Python de
`src/` e `tests/` validada por `ast.parse`. Nenhuma divergência entre
`database/code/` e `database/supabase/schemas/`.

**A suíte completa não foi concluída nesta rodada.** Sua execução foi
interrompida antes do fechamento; progresso parcial não comprova aprovação.
Não houve aplicação de migrations nem escrita no Supabase remoto.
PostgreSQL 18.6 foi extraído e inicializado em `/tmp`, mas a sandbox bloqueou
a abertura do socket. A validação de banco real desta rodada permanece pendente.

## Próxima rodada: quatro falhas reproduzidas

Reproduções preservadas em `test_pending_remote_merge.py`, neste diretório.
Estão separadas da suíte de aceite para documentar explicitamente o trabalho
inacabado, por pedido de publicação do progresso. Não foram corrigidas nem
marcadas como aprovação. Resultado observado antes da organização: **4 failed,
3 passed**.

1. `detail_requested` não está conectado à `MovementDetailsPage` na janela.
2. O filtro de usuário espera a posição 10, mas os adaptadores de movimentação
   ainda entregam dez campos e não fornecem o autor. Não consultar o diretório
   administrativo para STOCK: esse papel não possui a permissão correspondente.
3. O formulário interpreta máximo `0` como ausência e altera o dado na edição.
4. `NovoProdutoPage.load_product` não inicializa `maximum` ao receber a tupla
   de oito campos do estoque, gerando `UnboundLocalError`.

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
  .venv/bin/python -m pytest \
  docs/auditoria/2026-10-19/test_pending_remote_merge.py -q --tb=short
```

Depois dessas correções, executar a suíte completa, os verificadores
`scripts/verify_postgres.py` nos dois modos, `scripts/verify_sales.py`, os
testes de integração com `STOCKFLOW_TEST_DSN` local e `scripts/check_visual.py`.
Conferir histórico remoto antes de aplicar a migration renomeada; push Git
não aplica migrations ao Supabase.

## Recuperação local

- Backup desta integração: `/tmp/stockflow-sync-20261019` (temporário).
- Stash mantido: mensagem `stockflow-local-fixes-before-sync-20261019`.
  É uma cópia anterior à integração; não reaplicar sobre o trabalho publicado.
- Registro durável no vault: cérebro StockFlow, debate de 19/10/2026.
