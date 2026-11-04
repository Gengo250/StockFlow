# Comprovante PDF legível — 03/11/2026

Corrigida a exportação que reduzia o texto a menos de 1 ponto de altura. O HTML usava `font-size` em pixels e o `QPdfWriter` exportava em 1.200 DPI: o conteúdo ficava minúsculo mesmo ocupando a largura da folha. Os testes anteriores verificavam apenas a assinatura `%PDF` e não a legibilidade.

Agora o corpo usa 11 pt; empresa e título usam 18 e 16 pt; o total usa 15 pt e os detalhes, 10 pt. A exportação usa uma resolução de layout de 96 DPI, mantendo texto vetorial, e a paginação automática do Qt aplica margens de 2 cm e números de página. As seções têm espaçamento explícito.

A tabela passou de sete para cinco colunas: produto e código ficam juntos; o subtotal bruto do item aparece abaixo da descrição. Quantidade, preço unitário, desconto e total continuam presentes. Cabeçalhos se repetem nas páginas seguintes. Valores altos preservam os centavos na mesma linha.

## Exemplos gerados pelo aplicativo

- [Comprovante demo](comprovante-demo.pdf), emitido a partir do serviço real sobre dados fictícios.
- [Prévia renderizada](comprovante-demo.png).
- [35 itens com descrições longas](comprovante-35-itens.pdf): sete páginas; todos os códigos presentes uma vez, sem texto fora das margens na inspeção por coordenadas.
- [Valores de R$ 99.999.999,99](comprovante-valores-altos.pdf): centavos íntegros no item, no resumo e no pagamento.

Os cenários de muitos itens e valores altos são dados sintéticos para verificar a diagramação. Não representam vendas gravadas. Nenhuma venda, estoque ou pagamento foi alterado pela emissão.

## Verificação

Os testes usam `QPdfDocument` do próprio PySide6 para ler o PDF final, medir a altura física do texto, conferir os seis valores monetários grandes, detectar duplicação/perda de itens e conferir a repetição do cabeçalho. `pdftoppm` e `pdftotext` foram usados para inspeção visual e de coordenadas. Nenhuma dependência foi adicionada ao projeto.

Seleção de comprovante, renderer, domínio e caixa: **72 testes passaram**. A suíte geral final teve **1.610 aprovações, 53 skips e nenhuma falha**, registrada nos logs `pytest-final-0.log` a `pytest-final-3.log`, com JUnit correspondente. A integração PostgreSQL ficou fora desta rodada.

```sh
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
PYTHONPATH=src .venv/bin/python docs/ui/2026-11-03-comprovante/capture.py

QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
.venv/bin/python -m pytest tests/test_us19_comprovante_ui.py \
tests/unit/test_receipt_renderer.py tests/unit/test_sale_receipt.py -q
```

Impressora física não foi acionada. Os comandos `uv run stockflow --mock` e `STOCKFLOW_BACKEND=supabase uv run stockflow` permanecem iguais. A correção anterior do caixa está [documentada aqui](../2026-11-03-caixa/README.md).

Referência: [subconjunto HTML suportado pelo Qt](https://doc.qt.io/qt-6/richtext-html-subset.html), incluindo fontes em pontos, espaçamentos e `<thead>` em tabelas com várias páginas.
