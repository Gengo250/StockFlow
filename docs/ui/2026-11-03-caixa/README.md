# Caixa demo: estabilidade visual e valores altos — 03/11/2026

Corrigidos o redimensionamento repetido do diálogo, os rótulos truncados com fonte ampliada, a falta de acesso aos campos em janela pequena e o Enter que acionava Atualizar. Os comandos permanecem `uv run stockflow --mock` e `STOCKFLOW_BACKEND=supabase uv run stockflow`.

## O que mudou

- O diálogo inicia limitado à área disponível da tela e mantém seu tamanho durante abertura, atualização, erro, fechamento e reabertura. Os botões ficam fora da área de rolagem.
- Os formulários têm quebra de rótulos e crescimento explícitos. Em 520×360 com fonte de 20 pontos, Tab percorre todos os campos, inclusive Justificativa.
- Mensagens de erro e resultado são trazidas para a área visível. A rolagem acompanha a alteração final da altura do texto, incluindo a quebra de linhas calculada posteriormente pelo Qt.
- Enter aciona Iniciar/Fechar caixa. Atualizar e Voltar não se tornam automaticamente a ação padrão.
- Valores monetários exibem separadores brasileiros sem substituir a pontuação da mensagem inteira.
- O excesso de valor é recusado antes de chamar o serviço. O editor admite mais dígitos que o teto de negócio para impedir que `100000000,00` se transforme silenciosamente em `10000000,00`. O limite aceito continua **R$ 99.999.999,99 por campo**; a validação do serviço permanece ativa.

## Ensaio solicitado com valores altos

O roteiro percorreu login demo → Vendas → botão Caixa → diálogo modal real, em Qt offscreen e no ambiente nativo Wayland/Fusion.

| Dado | Valor verificado |
|---|---:|
| Saldo inicial | R$ 99.999.999,99 |
| Dinheiro, débito, crédito, Pix, vale e outros | R$ 99.999.999,99 em cada campo |
| Total declarado | R$ 599.999.999,94 |
| Total esperado, sem vendas neste cenário | R$ 99.999.999,99 |
| Diferença | R$ 499.999.999,95 |
| Justificativa preservada no registro demo | 2.000 caracteres |

Sem justificativa, a divergência impede o fechamento e mantém os valores. Com justificativa, o fechamento foi concluído e os totais conferem em `Decimal`. A abertura com R$ 100.000.000,00 foi recusada, preservando o valor informado. O excesso em cada um dos seis pagamentos também impede fechar, mesmo com justificativa.

Foram testadas digitações de `100000000,00`, `1000000000,00` e `999999999999,99`: nenhuma abriu um caixa com um valor menor aceito silenciosamente. A correção não amplia o limite de negócio.

## Evidências e reprodução

- [Resultado nativo](wayland/result.json), [resultado offscreen](offscreen/result.json).
- [Caixa aberto](wayland/02-aberto.png), [fonte ampliada](wayland/06-fonte-ampliada.png), [erro visível](wayland/08-erro-visivel.png).
- [Valor acima do limite](wayland/09-acima-do-limite.png), [justificativa longa](wayland/11-justificativa-longa.png), [fechamento com valores altos](wayland/12-fechamento-valores-altos.png).
- [Roteiro executável](capture.py). Captura somente os diálogos desse processo, isola configurações e bloqueia conexões de rede. Ambos os resultados registram **zero tentativas de rede** e **Supabase não importado**.

```sh
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
PYTHONPATH=src .venv/bin/python docs/ui/2026-11-03-caixa/capture.py

# Ambiente gráfico nativo:
PYTHONPATH=src .venv/bin/python docs/ui/2026-11-03-caixa/capture.py

QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
.venv/bin/python -m pytest tests/test_cash_register_dialog.py -q
```

Os **16 testes do diálogo passaram**. A suíte geral final teve **1.607 aprovações, 53 skips e nenhuma falha**. As reproduções de teclado, tamanho da janela, fonte ampliada e valores acima do limite falharam antes das respectivas correções. A suíte geral foi dividida por arquivo em quatro processos com configurações Qt isoladas; resultados finais nos arquivos `pytest-final-0.log` a `pytest-final-3.log` e respectivos JUnit. Integração PostgreSQL não foi executada nesta rodada.

O ensaio nativo verifica geometria e renderização, com capturas das etapas; não é uma medição de todos os frames das animações do compositor. Conteúdo fora da área visível em janela pequena fica acessível por rolagem. A justificativa continua sendo um campo de linha única com navegação horizontal; seus 2.000 caracteres foram conferidos integralmente no registro, sem depender da parte visível.

Esta correção se limita ao caixa e não encerra os demais achados da [auditoria geral](../../auditoria/2026-11-03/README.md). Nenhuma migration, alteração remota, dependência ou comando Git foi executado.

Referências consultadas: [QFormLayout](https://doc.qt.io/qt-6/qformlayout.html) para políticas de crescimento/quebra e [QPushButton](https://doc.qt.io/qt-6/qpushbutton.html) para o comportamento de default/autoDefault.
