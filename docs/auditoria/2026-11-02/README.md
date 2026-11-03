# Auditoria das tarefas das capturas — 02/11/2026

**Veredito: as tarefas não estão cumpridas integralmente.** Caixa e devolução por itens têm lacunas de integração; a migration de caixa bloqueia o fechamento de vendas, inclusive no Supabase configurado. Histórico, comprovante de venda existente e os quatro relatórios funcionaram nos cenários descritos abaixo.

## Escopo e ambiente

- Projeto `/home/luccas/Projects/StockFlow`, branch `main`, HEAD `71444d7` (`Rebase - fix bugs`); árvore versionada limpa antes da auditoria.
- Fontes dos requisitos: as seis capturas fornecidas, de `10-03-21` até `10-04-18`. Foram consideradas somente as descrições visíveis, sem presumir critérios de aceite internos do Jira. O cabeçalho “Done 36” não comprova que todos os 36 cartões estejam legíveis nas imagens.
- Aplicação iniciada com `STOCKFLOW_BACKEND=supabase uv run stockflow`; o usuário autenticou pela própria janela, com perfil Administrador. Nenhuma senha foi coletada ou registrada.
- Testes de UI automatizados em PySide6 offscreen; interação adicional na janela nativa autenticada.
- PostgreSQL 18.6 temporário, somente em `127.0.0.1:55439`, extraído em `/tmp/stockflow-pg-audit`. Fixtures criam bancos descartáveis, executam schema/migrations separadamente e removem os bancos ao terminar.
- Não foram alterados código de produção, dependências versionadas, migrations nem dados existentes no Supabase. A tentativa de nova venda foi recusada; estoque continuou com 6 unidades do produto selecionado e histórico com 4 vendas. Os testes de escrita de caixa/devolução aconteceram exclusivamente no PostgreSQL descartável.

## Resultados executados

| Execução | Resultado | Evidência |
| --- | --- | --- |
| Suíte existente `tests/` | **1.578 passaram, 1 falhou, 33 pulados**, 722,62 s | [log](pytest.log), [JUnit](pytest.xml) |
| Integração existente com PostgreSQL real | **29 passaram, 3 falharam**, 2,00 s | [log](integration.log), [JUnit](integration.xml) |
| Novas verificações de aceite | **5 passaram, 9 falharam, 7 puladas**, 1,51 s | [fonte](test_acceptance_gaps.py), [log](acceptance.log), [JUnit](acceptance.xml) |
| Seleção de relatórios | **4 passaram**, 0,73 s | [log](reports.log) |
| Exportações na janela Supabase | 4 CSVs, colunas/UTF-8 BOM/totais conferidos | [validação](csv-validation.json), arquivos nesta pasta |
| Comprovante de venda Supabase | PDF de 1 página, conteúdo extraído e conferido | [PDF](comprovante-supabase.pdf), [texto](comprovante-supabase.txt) |

As contagens das execuções não devem ser somadas: há sobreposição. Na suíte geral, 32 skips eram integrações sem DSN, posteriormente executadas separadamente; o outro é um caso de permissão de ADMIN sem área inacessível. Nos testes novos, 7 skips correspondem ao caixa ausente no schema declarativo. As 9 falhas novas incluem reproduções diferentes de uma mesma causa; não representam nove defeitos independentes.

## Achados que impedem aceite integral

### A1 — Bloqueante: não é possível concluir vendas no Supabase

Reprodução nativa: Vendas → selecionar cliente ativo e `Monitor teste (PRD-002)` → finalizar uma unidade. Resultado: `Venda deve estar associada a uma sessão de caixa aberta.` O carrinho permanece e nenhuma venda nova aparece. [Captura](screenshots/supabase-venda-bloqueada.png).

A migration `20261101160524_us23_open_close_register.sql:138` exige `sales.register_log_id` em qualquer INSERT/UPDATE. As RPCs de venda, incluindo `fn_register_sale_with_discounts`, não recebem nem preenchem esse campo. Tampouco há tela de abertura/fechamento ou instância de `RegisterService` na apresentação.

O teste `test_checkout_works_with_open_cash[migrations]` abriu um caixa válido antes de vender e ainda reproduziu a mesma recusa. Portanto, abrir manualmente um caixa não resolve a ligação ausente. Dois testes existentes de desconto também falham por esse motivo; um terceiro teste de histórico falha ao inserir vendas sem o novo vínculo.

**Afeta:** US23/SCRUM-242 e 244; impede validar US22 de ponta a ponta e novas vendas usadas pelas demais histórias.

### A2 — Alta: abertura e fechamento de caixa sem autenticação

No banco criado por todas as migrations, `SET LOCAL ROLE anon` conseguiu executar abertura e fechamento reais de um caixa de teste. As funções são `SECURITY DEFINER`, não verificam identidade/papel/empresa e não revogam EXECUTE de PUBLIC na migration.

No Supabase, foram feitas apenas sondagens sem efeitos persistentes: abertura com saldo negativo e fechamento com UUID aleatório inexistente. Ambas chegaram à validação interna (`P0001`), em vez de recusar acesso (`42501`). [Respostas](remote-anonymous.json). A criação/fechamento anônimos efetivos foram reproduzidos somente localmente, sem explorar caixas remotos.

**Afeta:** autorização e isolamento do fluxo US23. Não confundir a existência da RPC com um fluxo seguro para uso.

### A3 — Alta: sessão única falha com concorrência

`test_concurrent_open_keeps_single_session[migrations]` sobrepôs duas transações reais no mesmo caixa/operador. A segunda aguardou lock da primeira; depois dos commits, havia **2 sessões OPEN**.

Os índices de operador/caixa aberto são comuns, não UNIQUE; `IF EXISTS` antes do INSERT não protege contra duas aberturas simultâneas. A recusa sequencial funciona, mas não garante a regra prometida.

**Afeta:** SCRUM-241.

### A4 — Alta: devolução por itens não está conectada à interface

`ReturnService`, `ReturnEligibilityService`, DTOs e RPCs existem. Entretanto, `SaleDetailsPage._pedir_devolucao` (`sale_details.py:454`) pede somente um motivo; `MainWindow._devolver_venda` (`main_window.py:576`) chama `SaleService.return_sale`, que usa a reversão total legada. A tela não permite selecionar itens/quantidades nem consultar o saldo ainda devolvível.

No PostgreSQL via migrations, uma venda preparada diretamente com vínculo de caixa permitiu testar a RPC nova: retorno parcial de R$20, restituição de uma unidade, repetição idempotente e recusa de quantidade excedente passaram, sem duplicar movimentos/registros após erro. Essa preparação isola a US20 da falha de checkout; **não prova que a operação esteja acessível pelo aplicativo**.

O valor da devolução é registrado em `returns.total_amount` na mesma transação dos itens e movimentos. Não existe ligação desse valor ao cálculo de fechamento de caixa: `fn_close_register_session` soma vendas concluídas e não consulta `returns`. Liquidação/restituição financeira efetiva não foi comprovada.

**Afeta:** SCRUM-231 e aceite integrado da US20; SCRUM-234 fica parcial.

### A5 — Alta: schema declarativo e migrations produzem capacidades diferentes

A suíte existente detecta nove objetos de caixa ausentes em `database/code`: tabela `register_log`, três funções, quatro índices e um trigger. O schema declarativo não tem a regra de caixa que as migrations aplicam.

Além disso, no schema declarativo, um ADMIN autenticado recebe `permission denied for function fn_return_partial_sale`. A allowlist em `database/code/policies/01_security.sql:225` inclui a devolução legada, mas não as RPCs novas de devolução. Nas migrations, os grants correspondentes existem.

**Afeta:** SCRUM-240 e a implantação/execução da US20. Não aplicar sync/migrations como “correção” sem reconciliar as fontes.

### A6 — Média: comprovante aceita total pago inconsistente

O fluxo normal e o PDF real funcionaram. Entretanto, `test_receipt_rejects_inconsistent_payment_total` forneceu bruto/itens de R$100, desconto zero e total pago R$1. O domínio gerou o comprovante em vez de recusar a inconsistência; ele não compara o total pago com o líquido calculado.

É um achado defensivo, reproduzido com dados sintéticos inconsistentes, não uma inconsistência observada na venda remota. Validação de status pendente e marcação de cancelamento têm testes existentes aprovados.

## Matriz das histórias e subtarefas visíveis

“Atendido nos testes” limita-se aos cenários executados, sem substituir critérios de aceite não presentes nas capturas.

| História | Avaliação |
| --- | --- |
| **US23 — Abrir/fechar caixa (216)** | **Não atendida integralmente.** Sem fluxo de UI, vínculo com vendas ausente, concorrência e autorização falham. |
| **US20 — Devolução (214)** | **Parcial.** Backend novo existe, mas interface usa reversão total antiga; schema declarativo nega a RPC nova. |
| **US19 — Comprovante (213)** | **Fluxo principal atendido**, inclusive PDF real; ressalva A6 para dados inconsistentes. |
| **US17 — Histórico (212)** | **Atendido nos testes de consulta/detalhes/bloqueio de edição**; integração da criação das vendas sofre A1. |
| **US26 — Exportação (217)** | **Atendida nos cenários executados:** quatro tipos, colunas, totais e codificação; filtros cobertos por testes de UI. |
| **US22 — Descontos (215)** | **Parcial no sistema integrado.** Cálculo/regras/autorização têm testes aprovados, mas a venda com descontos falha nas migrations/Supabase por A1. |

| Cartão | Requisito visível | Resultado/evidência |
| --- | --- | --- |
| SCRUM-240 | Modelo de sessão e saldos por pagamento | Parcial: migration existe, schema declarativo não; A5. |
| SCRUM-241 | Abertura com sessão única | Falha concorrente A3; recusa sequencial passou. |
| SCRUM-242 | Integrar pagamentos ao caixa aberto | Falha A1: checkout não vincula a sessão. |
| SCRUM-243 | Fechamento, diferenças e justificativa | Cálculo básico e justificativa testados localmente; sem UI e com falha de autorização A2. Não aprovado integralmente. |
| SCRUM-244 | Bloquear venda sem caixa e alterações após fechamento | Guarda SQL presente e bloqueio sem caixa reproduzido; falta integração para uma venda válida. |
| SCRUM-230 | Modelo de devoluções e itens | Presente em schema/migrations; persistência local conferida. |
| SCRUM-231 | Seleção da venda e quantidade devolvível | Parcial: RPC/serviço existem, seleção de itens ausente da UI; A4/A5. |
| SCRUM-232 | Restituir estoque e movimentação | Passou em RPC local isolada e testes de repositório; falta integração da UI. |
| SCRUM-233 | Preços/descontos originais | Cálculo e preservação cobertos por testes de domínio/repositório; fluxo completo pela UI não disponível. |
| SCRUM-234 | Devolução, estoque e registros financeiros em transação | RPC grava retorno/itens/valor/movimento atomicamente; idempotência/recusa excedente verificadas. Integração financeira com caixa não comprovada; A4. |
| SCRUM-224 | Layout e gerador do comprovante | Passou; PDF real salvo e lido. |
| SCRUM-225 | Empresa, venda, itens, cliente, pagamentos | Dados presentes na venda remota e testes de composição aprovados. |
| SCRUM-227 | Validar status antes de emitir | Testes de bloqueio de pendente aprovados. |
| SCRUM-228 | Reemitir preservando dados originais | Emissão de venda antiga no Supabase e testes de snapshots aprovados. |
| SCRUM-229 | Mostrar cancelamento quando aplicável | Testes do domínio/renderizador/UI aprovados; sem cancelar venda histórica remota para testar. |
| SCRUM-245 | Gerador CSV reutilizável | Usado nos quatro arquivos reais; `application/services/csv_exporter.py`. |
| SCRUM-246 | Mapear colunas de cada relatório | Cabeçalhos e largura das linhas conferidos nos quatro CSVs. |
| SCRUM-247 | Integrar quatro relatórios | Estoque, vendas, movimentações e auditoria exportados no Supabase. |
| SCRUM-248 | Testar filtros, totais e codificação | Testes de filtros aprovados; totais reais e UTF-8 BOM conferidos. |
| SCRUM-235 | Desconto percentual e fixo | Testes de aritmética e UI aprovados; gravação integrada bloqueada por A1. |
| SCRUM-236 | Limite por perfil | Passou com PostgreSQL declarativo; checkout das migrations falha por A1. |
| SCRUM-237 | Autorizar acima do limite | Reautenticação/auditoria passaram no declarativo; não concluível nas migrations por A1. |
| SCRUM-238 | Recalcular subtotais, total, pagamentos | Testes locais aprovados; fluxo de venda real bloqueado. |
| SCRUM-239 | Registrar desconto e responsável | Campos/testes de auditoria aprovados no declarativo; gravação nas migrations bloqueada. |
| SCRUM-84 (H09) | Consulta paginada de vendas | Testes de paginação aprovados; tratar como a descrição visível, sem reinterpretar H09. |
| SCRUM-218 (H17) | Consulta paginada de vendas | Testes de três páginas, filtros e ordenação aprovados; banco remoto tinha apenas quatro vendas. |
| SCRUM-223 | Bloquear edição de confirmadas | Tabela não editável e detalhe sem edição; testes aprovados. Cancelamento/devolução são operações separadas. |
| ID cortado na primeira captura | Tela de detalhes com itens, pagamento e cliente | Aberta na janela autenticada; [captura](screenshots/supabase-detalhe.png). |

## Evidências dos relatórios

- Estoque: 4 produtos, 173 unidades, incluindo um inativo; dashboard de ativos mostrou 153 unidades, diferença esperada pelo filtro.
- Vendas: 4 registros, R$380,00; média R$95,00. Filtro nativo por cliente Roberto: uma linha/R$230,00, também exportada e conferida em `relatorio_vendas_filtrado_2026-11-02.csv`.
- Movimentações: 12 registros; entradas confirmadas 189 e saídas confirmadas 16.
- Auditoria: 2 alterações, 1 produto, 2 campos.
- Todos os CSVs contêm BOM UTF-8, delimitador `;` e cabeçalhos correspondentes; acentuação preservada. O CSV de vendas usa números com ponto decimal, ao contrário da formatação monetária visual brasileira, e foi validado como número decimal.
- Capturas nativas em [screenshots](screenshots/). Não houve impressão física; a saída PDF foi verificada.

## Como reproduzir

Na raiz do projeto, com dependências já instaladas:

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion \
  uv run --frozen python -m pytest tests/ -q --tb=short

# DSN deve apontar somente para PostgreSQL local descartável:
STOCKFLOW_TEST_DSN='host=127.0.0.1 port=55439 dbname=postgres user=luccas' \
  uv run python -m pytest tests/integration -q --tb=short

STOCKFLOW_TEST_DSN='host=127.0.0.1 port=55439 dbname=postgres user=luccas' \
  uv run python -m pytest docs/auditoria/2026-11-02/test_acceptance_gaps.py -q --tb=short

STOCKFLOW_BACKEND=supabase uv run stockflow
```

Os testes novos expressam expectativas de aceite e deixam as falhas visíveis, sem `xfail`. Não foram feitas correções, commit ou push. Prioridade sugerida: fechar autorização/concorrência do caixa, integrar sessão ao checkout e à UI, reconciliar schema/migrations e conectar a devolução por itens; então repetir os fluxos completos com todos os perfis.
