# Revisão da main e do modo demo — 2026-11-03

O fluxo básico do demo funciona: login, navegação, abertura de caixa, venda, comprovante PDF, relatórios CSV e fechamento sem diferença. **A revisão não aprova a integridade de todos os fluxos**: foram reproduzidas falhas de estoque, reversão de vendas, usuários e contratos de leitura.

O usuário esclareceu que deseja **testar/revisar o demo mantendo os comandos**. Foram preservados `uv run stockflow --mock` e `STOCKFLOW_BACKEND=supabase uv run stockflow`. A revisão inicial não alterou código de produção, testes existentes, tags ou releases; os arquivos desta pasta são evidências e reproduções dessa revisão. A correção posterior dos bugs visuais do caixa e o ensaio com valores altos estão registrados [separadamente](../../ui/2026-11-03-caixa/README.md).

## Base e alcance

- `main` local: `22df8355a295361847d90202e271ece8b3db8a8c`, `adding the option to open and close caixa`. A referência local `origin/main` apontava ao mesmo commit.
- Não foi possível confirmar a versão remota: a consulta por SSH retornou `Permission denied (publickey)`. Não houve fetch, push, commit ou acesso ao Supabase remoto.
- Inventário de **463 arquivos próprios** de código/configuração; análise sintática de **281 arquivos Python/spec**, sem erros; nenhuma divergência nos **43 pares SQL** entre `database/code` e `database/supabase/schemas`. Isso não prova equivalência com a sequência de migrations.
- Revisão manual dos contratos e caminhos relevantes de apresentação, autenticação/permissões, produtos, movimentações, vendas, caixa, devoluções, comprovantes, relatórios, adaptadores Supabase, SQL, CLI e CI. O inventário é abrangente; não representa verificação formal de cada linha. Dependências em `vendor/` e ambientes virtuais ficaram fora da revisão de código próprio.
- UI executada com PySide6 real e `QT_QPA_PLATFORM=offscreen`, configurações/cache temporários. As capturas mostram renderização; não foi teste manual em uma sessão gráfica nativa.
- Sem `STOCKFLOW_TEST_DSN`: integração PostgreSQL não executada. Os testes locais do adaptador Supabase usam respostas simuladas.

## Verificação executada

| Verificação | Resultado | Evidência |
|---|---|---|
| Suíte existente `pytest tests/` | **1593 passed, 53 skipped**, 445,30 s (revisão inicial) | [Log](pytest.log), [JUnit](pytest.xml) |
| Aceite adicional do demo | **9 falhas, 2 aprovações**, 13,79 s | [Testes](test_demo_review.py), [log](acceptance.log), [JUnit](acceptance.xml) |
| Contrato adicional do adaptador Supabase | **1 falha**, 0,04 s; sem rede | [Teste](test_supabase_review.py), [log](adapter.log), [JUnit](adapter.xml) |
| Executável `uv run --offline --frozen stockflow --mock` | **Aprovado** | [Roteiro](smoke_cli.py), [resultado](smoke-cli.json), [log](smoke-cli.log) |
| Inventário/sintaxe/espelhos SQL | Sem erro sintático ou diferença entre espelhos | [Inventário](inventory.json) |

Os testes adicionais expressam o comportamento esperado e ficam vermelhos enquanto os defeitos estão abertos. Eles estão separados de `tests/`; não foram ocultados com `xfail`, nem houve relaxamento de testes existentes. Uma primeira execução da suíte foi interrompida para reiniciar com configuração Qt isolada; somente a execução concluída acima conta como resultado.

O smoke percorreu **11 áreas**, vendeu uma unidade por **R$ 2.499,90 via PIX**, gerou um PDF, exportou os quatro tipos de relatório e fechou o caixa com **diferença R$ 0,00**. Mesmo com `STOCKFLOW_BACKEND=supabase` no ambiente do subprocesso, `--mock` selecionou o demo: **zero tentativas de conexão** e **cliente Supabase não importado**. Não é uma prova de persistência no banco; os dados deste fluxo são locais e fictícios.

## Achados reproduzidos

Prioridades: **P1** = corrigir antes de confiar na integridade dos fluxos afetados; **P2** = defeito funcional/contrato a corrigir na sequência. A prioridade considera o contexto demonstrativo; nenhum achado abaixo prova exploração ou corrupção do banco remoto.

### R01 — P1: devolução com vários itens deixa estoque parcialmente alterado após erro

**Fonte:** `src/stockflow/infrastructure/repositories/demo_movement_repository.py:208` (`reverse_sale`) e `demo_sale_repository.py:364` (`_reverter`).

**Reprodução:** vender `PRD-009` e `PRD-008`, desativar o segundo produto e devolver a venda pelo handler da janela. O primeiro item gera entrada; o segundo lança erro. A venda continua `CONCLUIDA`, mas o estoque de `PRD-009` já voltou de 17 para 18. A operação não restaura o estado anterior à falha.

**Impacto:** nova tentativa pode repor novamente o primeiro item, e estoque/movimentações passam a contradizer o estado da venda. O lock serializa operações, mas não oferece rollback.

**Direção de correção:** validar todos os itens antes de gravar e aplicar a reversão inteira com rollback de estoque, movimentos e venda em qualquer falha.

**Teste:** `test_failed_multi_item_return_is_atomic`.

### R02 — P1: cadastro/edição de produto escrevem saldo fora do histórico de movimentos

**Fonte:** `src/stockflow/infrastructure/repositories/demo_product_repository.py:197` e `:201` (`create`/`update`).

**Reproduções:**

1. Cadastrar um produto pelo formulário real, usando o código gerado pela aplicação, com estoque inicial 7: catálogo exibe 7, mas não existe nenhuma movimentação confirmada desse produto.
2. Abrir edição de `PRD-009` com saldo 18, registrar uma venda que reduz o saldo para 17 e salvar apenas a mudança de nome no formulário já aberto: o saldo retorna a 18, embora a saída da venda permaneça confirmada.

**Impacto:** saldo deixa de corresponder ao histórico; salvar dados cadastrais pode apagar o efeito de uma venda. O cenário inicial do demo cria movimentos de abertura, mas o cadastro posterior não segue o mesmo contrato.

**Direção de correção:** criar o saldo inicial por movimentação e preservar o saldo corrente na edição cadastral. Ajustes intencionais de quantidade devem usar o serviço de movimentações. Existem testes antigos que esperam edição direta de saldo; será necessário reconciliar esse contrato explicitamente, sem simplesmente alterar asserts para esconder o problema.

**Testes:** `test_created_product_stock_has_confirmed_movement`, `test_product_edit_does_not_erase_a_sale_made_after_form_opened`.

### R03 — P1: demo permite cancelar venda de caixa já fechado

**Fonte:** `src/stockflow/infrastructure/repositories/demo_sale_repository.py:364`. Contrato SQL de comparação: `database/code/procedures/20_register_sessions.sql:225`.

**Reprodução:** abrir caixa, registrar venda, fechar com o total correto e cancelar essa venda. O demo aceita o cancelamento; o registro de fechamento continua com o total originalmente conferido. O SQL possui trigger que recusa inserção/alteração de venda quando o caixa está fechado.

**Impacto:** vendas/estoque mudam depois da conferência, sem que o fechamento seja refeito. A demonstração aceita uma ação que o backend SQL pretende recusar.

**Direção de correção:** verificar o estado do caixa associado à venda antes de qualquer reversão e testar cancelamento/devolução depois do fechamento.

**Teste:** `test_closed_register_sale_cannot_be_changed`.

### R04 — P2: cancelamento total não invalida o snapshot de devolução parcial

**Fonte:** `src/stockflow/infrastructure/repositories/demo_sale_repository.py:200`, `:245`, `:364`.

**Reprodução de contrato:** com uma sessão que contém empresa válida, vender, cancelar totalmente e chamar `partial_return` para o mesmo item. A chamada é aceita: `_reverter` muda a linha em `rows`, mas `_return_sales` conserva o snapshot como concluído.

**Impacto:** os caminhos antigo e novo de devolução podem restituir a mesma unidade mais de uma vez.

**Limite da evidência:** o teste fornece uma empresa válida para isolar o contrato US20. O login demo normal não fornece `company_id`, e a UI atual não conecta o serviço de devolução parcial (R10). Não se afirma que essa sequência esteja disponível por cliques na versão atual.

**Direção de correção:** manter uma fonte consistente para status e quantidades devolvidas, sincronizando a reversão total com o estado consultado pela devolução parcial.

**Teste:** `test_cancelled_sale_cannot_return_items_again`.

### R05 — P2: último administrador pode perder o próprio papel no demo

**Fonte:** `src/stockflow/presentation/backend.py:337` (`save_user`).

**Reprodução:** editar o único ADMIN para SELLER. A operação é aceita e altera a conta usada na próxima autenticação. A proteção existente contra desativação do último administrador não cobre a troca de papel.

**Impacto:** a execução demonstrativa fica sem acesso administrativo após novo login. Reiniciar o processo restaura as contas iniciais; não é perda permanente de conta remota.

**Direção de correção:** aplicar a preservação de pelo menos um administrador ativo também à edição de papel, considerando o estado atual das contas.

**Teste:** `test_last_admin_cannot_demote_itself`.

### R06 — P2: usuário editado e desativado continua listado como ativo

**Fonte:** `src/stockflow/presentation/backend.py:219` e `:367`.

**Reprodução:** editar o departamento do vendedor e depois desativá-lo. A autenticação recusa corretamente a conta, mas a linha da listagem mantém `Ativo`.

**Causa/impacto:** `build_demo_user_directory` calcula o estado atualizado e depois o sobrescreve com a cópia antiga de `_demo_users`. A tela apresenta situação incompatível com a autenticação e orienta incorretamente a próxima ação administrativa.

**Direção de correção:** derivar a situação da fonte de status corrente ao montar as linhas, preservando apenas os campos cadastrais editados.

**Teste:** `test_edited_user_status_matches_authentication`.

### R07 — P2: ordenação de vendas por data ignora o horário

**Fonte:** `src/stockflow/infrastructure/repositories/demo_sale_repository.py:72` e `:94`.

**Reprodução:** duas vendas no mesmo dia, às 17:30 e às 08:30, com UUIDs em ordem inversa. `DATA_DESC` devolve a venda das 08:30 primeiro, pois a chave usa apenas os dez primeiros caracteres da data e desempata pelo ID.

**Direção de correção:** ordenar pelo instante completo e usar o ID apenas quando o instante também empatar. Os filtros por dia podem continuar usando uma conversão separada para `date`.

**Teste:** `test_same_day_history_uses_time_before_id`.

### R08 — P2: comprovante aceita total de pagamento incompatível com a venda

**Fonte:** `src/stockflow/domain/sale_receipt.py:154`.

**Reprodução defensiva:** obter uma venda legítima de R$ 2.499,90, alterar somente `total` para `0.01` na resposta simulada e montar o comprovante. Ele mantém líquido de R$ 2.499,90 e pagamento de R$ 0,01 sem lançar `ReceiptNotAvailable`.

**Impacto:** dados inconsistentes recebidos do repositório podem gerar comprovante contraditório. Não foi observada geração dessa corrupção no fluxo normal de venda.

**Direção de correção:** verificar as igualdades entre itens, bruto, descontos, líquido e pagamento antes de emitir, usando a mesma precisão monetária do domínio.

**Teste:** `test_receipt_rejects_total_that_disagrees_with_items`.

### R09 — P2: leitura individual Supabase perde mínimo e máximo de estoque

**Fonte:** `src/stockflow/infrastructure/repositories/supabase_product_repository.py:194` e `product_mapper.py:96`.

**Reprodução sem rede:** uma resposta de `product_stock` contém mínimo 10 e máximo 20. `fetch_catalog` preserva ambos; `get` devolve ambos como `None`.

**Causa:** `_minimums` passou a retornar pares `(min, max)`. `get` ainda passa o par inteiro para `minimum_stock` e omite `maximum_stock`; o normalizador descarta o par como inválido.

**Impacto:** consultas pelo código retornam limites diferentes da listagem para o mesmo produto, afetando consumidores dessa leitura.

**Direção de correção:** desempacotar os dois valores em `get`, com o mesmo tratamento de ausência de `fetch_catalog`.

**Teste:** `test_supabase_review.py::test_single_product_preserves_same_stock_limits_as_catalog`.

## Observações por inspeção de código

Estas observações não são resultados de execução no Supabase remoto.

### R10 — P2: devolução parcial ainda não é um fluxo disponível na UI/demo normal

`src/stockflow/presentation/windows/main_window.py:591` chama `SaleService.return_sale`, o fluxo de devolução total. `presentation/pages/sale_details.py:454` solicita apenas motivo, sem seleção de itens/quantidades. A camada de apresentação não instancia os novos serviços de devolução parcial/elegibilidade.

Além disso, `presentation/demo_accounts.py:31` cria sessão sem empresa, enquanto `domain/permissions.py:357` exige `company_id` para esses serviços. A existência de classes e testes US20 não prova entrega funcional pela aplicação. Conectar o fluxo exige tratar sessão demo, seleção de itens, elegibilidade, idempotência e integração com o estado da venda.

### R11 — P2: permissões US20 divergem entre declarativo e migrations

`database/code/procedures/08_return_partial.sql:282` e `09_get_returnable_items.sql:54` revogam execução de `authenticated`/`app_backend`. A lista de concessões de `database/code/policies/01_security.sql` não inclui essas duas RPCs; `02_returns_security.sql` concede apenas leitura das tabelas. As migrations `20261030101000_us20_return_rpcs.sql` e `20261030120000_us20_return_idempotency.sql` concedem execução das RPCs.

Um banco construído pelo caminho declarativo, portanto, tem contrato de acesso diferente do construído pelas migrations. É necessário decidir se US20 deve ser publicada agora e alinhar os dois caminhos, verificando privilégios efetivos com a role da aplicação. Não foi inferido o estado do banco implantado.

### R12 — P2: caminho padrão do script fiscal não existe

`src/stockflow/infrastructure/fiscal/nfe_client.py:11` sobe até `src/` e procura `src/services_fiscal_php/cli_emitir.php`; o arquivo está em `src/stockflow/services_fiscal_php/cli_emitir.php`. A existência dos caminhos foi conferida.

O PHP também não está instalado neste ambiente, portanto não houve execução dessa integração. O fluxo atual de venda múltipla não chama esse cliente; há chamadas no caminho legado de venda e na edição Supabase de produto. O script PHP produz resposta simulada de autorização, sem comprovação de emissão externa. O PDF validado nesta revisão é o comprovante não fiscal do aplicativo.

### Manutenção: método duplicado em SupabaseSaleRepository

`register_items` aparece em `src/stockflow/infrastructure/repositories/supabase_sale_repository.py:217` e `:387`. A segunda definição substitui a primeira, deixando código morto e dificultando identificar o caminho efetivo. A suíte não prova execução da primeira implementação, que nunca é escolhida por Python.

## Evidências visuais e exportações

- [Login](screenshots/login.png)
- [Abertura de caixa](screenshots/caixa-abertura.png)
- [Venda concluída](screenshots/venda-concluida.png)
- [Comprovante](screenshots/comprovante.png) e [PDF gerado](comprovante-demo.pdf)
- [Caixa fechado sem diferença](screenshots/caixa-fechado.png)
- [Relatório de auditoria](screenshots/relatorio-auditoria.png)
- CSVs: [estoque](estoque.csv), [vendas](vendas.csv), [movimentações](movimentacoes.csv), [auditoria](auditoria.csv)

## Como reproduzir

Executar a partir da raiz do projeto, com as dependências já disponíveis em `.venv`:

```sh
# Suíte existente; integração SQL é ignorada se STOCKFLOW_TEST_DSN não estiver definida.
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
XDG_CONFIG_HOME=/tmp/stockflow-review-config XDG_CACHE_HOME=/tmp/stockflow-review-cache \
STOCKFLOW_BACKEND=demo .venv/bin/python -m pytest tests/ -q --tb=short

# Reproduções adicionais: esperadas vermelhas no commit revisado.
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
PYTHONPATH=src .venv/bin/python -m pytest \
docs/auditoria/2026-11-03/test_demo_review.py \
docs/auditoria/2026-11-03/test_supabase_review.py -q --tb=short

# Smoke do executável; gera capturas, PDF, CSVs e resultado JSON nesta pasta.
.venv/bin/python docs/auditoria/2026-11-03/smoke_cli.py
```

O smoke usa `--offline --frozen` para aproveitar o ambiente e lock existentes durante a auditoria; isso não altera o comando normal de uso `uv run stockflow --mock`.

## Ordem sugerida para correção

1. Tornar reversões e alterações de saldo consistentes (R01/R02) e proteger vendas de caixa fechado (R03).
2. Unificar o estado de devoluções total/parcial (R04), antes de conectar US20 à interface (R10/R11).
3. Corrigir administração de usuários, ordenação, validação do comprovante e limites de produto (R05–R09).
4. Corrigir/definir o alcance da integração fiscal e remover o método morto em uma mudança separada.

O fluxo de caixa recém-adicionado está presente e passou no caminho normal. Ausência de UI de caixa apontada em revisões anteriores não deve ser repetida como achado desta versão.
