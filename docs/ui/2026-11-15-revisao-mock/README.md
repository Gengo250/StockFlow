# Revisão visual do StockFlow mockado — 15/11/2026

## Escopo

Aplicação iniciada com `--mock`, configuração temporária isolada e dados
fictícios. O login de demonstração e a navegação por dashboard, estoque,
movimentações, compras, usuários e vendas foram exercitados automaticamente
com a janela real no Wayland, em 1024 × 768. As capturas mostram somente a
janela do aplicativo. Também foram geradas capturas offscreen em 1024 × 768,
1366 × 768 e 1440 × 900, incluindo formulários e estados vazio e de erro.
O roteiro foi automatizado; não substitui avaliação manual de acessibilidade.

## Problemas observados

1. **Usuários — nomes e ações ilegíveis em 1024 × 768.** A primeira e a última
   coluna encolhem e o botão de ativação fica estreito demais para seu texto;
   os ícones se sobrepõem. A célula de ações mediu 77 px e o botão Desativar,
   19 px. Em 1440 × 900 os elementos ficaram visíveis. Evidências:
   [1024 Wayland](usuarios-1024-wayland.png) e
   [1440 offscreen](usuarios-1440-offscreen.png).
2. **Movimentações — controles saem da área visível em 1024 × 768.** Os
   botões de confirmar e ajustar e os filtros são cortados à direita; é
   preciso rolar horizontalmente. A página mediu 881 px para um viewport de
   776 px, com 105 px de rolagem horizontal. Em 1366 × 768 e 1440 × 900 não
   houve rolagem horizontal nessa página. Evidência:
   [1024 Wayland](movimentacoes-1024-wayland.png).
3. **Compras — estilo visual inconsistente.** Campos, tabela e botões usam
   aparência padrão do Qt, diferente das demais telas; há também uma caixa
   de aviso vazia. O mesmo aspecto apareceu nas capturas 1024 e 1440.
   Evidência: [1024 Wayland](compras-1024-wayland.png).
4. **Vendas — campos de pagamento parcialmente ocultos.** Na abertura da
   tela em 1024 × 768, os campos aparecem cortados na parte inferior da área
   de nova venda. Há rolagem vertical interna, mas sua presença e a divisão
   entre formulário e botão de finalizar dificultam a leitura do fluxo.
   Evidência: [1024 Wayland](vendas-1024-wayland.png).
5. **Fornecedores — cabeçalho e conteúdo comprimidos em 1024 × 768.** O
   primeiro título da tabela aparece cortado e nomes, telefones e endereços
   aparecem abreviados em colunas estreitas. Evidência:
   [1024 offscreen](fornecedores-1024-offscreen.png).

Essas observações são problemas de apresentação ou usabilidade, não provam
falha na persistência ou nas regras de negócio. Nenhuma correção de código
foi aplicada nesta revisão.

## Verificações executadas

```bash
QT_QPA_PLATFORM=offscreen STOCKFLOW_BACKEND=demo \
  .venv/bin/python -m pytest tests/test_ui_content_bounds.py \
  tests/test_window_viewport.py tests/test_ui_regression.py \
  tests/test_feature_ui.py tests/test_mock_application.py -q -p no:cacheprovider
```

**25 passaram.** Também foram executados `scripts/check_visual.py` e
`docs/ui/2026-10-23/capture.py`, que geraram respectivamente 72 e 67 capturas,
sem comparação automática com uma referência. Os testes existentes aprovados
não detectam todos os problemas identificados pela inspeção das imagens.
As capturas offscreen completas estão temporariamente em
`/tmp/stockflow-visual-capture/screenshots/` e
`/tmp/stockflow-visual-extra/screenshots/` e podem ser apagadas pelo sistema.
