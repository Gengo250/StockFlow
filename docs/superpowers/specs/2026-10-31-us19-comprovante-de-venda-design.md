# US19 — Emitir comprovante de venda (SCRUM-213)

Data: 2026-10-31
Sprint 3 · 5 pontos

## Problema

Depois de confirmar uma venda, o operador não tem o que entregar ao cliente.
O StockFlow registra a operação (US10/US12), lista o histórico (US17) e aplica
descontos (US22), mas nada produz o documento que serve de referência para
troca, devolução e conferência de valores.

## O que já existe

A investigação encontrou mais pronto do que pendente. O que segue é o
inventário que decide o escopo real desta história.

### A leitura da venda já é única e completa

`fn_list_sales` (US17, `database/code/procedures/07_clients_sales.sql`)
devolve, numa consulta só: `id`, `created_on`, `client_id`, `client_name`,
`seller_id`, `seller_name`, `payment_method`, `discount`, `original_total`,
`total`, `status`, `items` (cada um com `product_code`, `product_name`,
`quantity`, `unit_price`, `subtotal`, `discount_type`, `discount_value`,
`discount_amount`, `final_subtotal`) e o vínculo de reversão
(`reversal_kind`, `reversal_reason`, `reversal_on`, `reversal_by_name`).

`SaleRepository.get` → `SaleService.get_sale` é o caminho que a tela de
detalhe já usa. O comprovante usa o MESMO caminho. Nenhuma consulta nova
sobre venda, item, cliente ou vendedor é necessária (SCRUM-225).

### O snapshot histórico do SCRUM-228 já é regra do schema

`database/code/tables/06_clients_sales.sql` congela, no momento da gravação:

- `sales.client_name` — sobrevive à renomeação do cliente;
- `sale_items.product_name` / `product_code` / `unit_price` — sobrevivem à
  exclusão do produto (FK `ON DELETE SET NULL`);
- `sales.discount`, `sales.total`, `sales.original_total`,
  `sale_items.discount_amount`, `sale_items.final_subtotal`.

Reemitir é reler essas colunas. Não existe nada a construir para preservar o
dado histórico: ele já é preservado, e reusar isso é literalmente o que o
SCRUM-228 pede.

### Os status já cobrem a validação

`domain/enums/sale_status.py` e `public.sale_status`: `PENDENTE` (carrinho em
montagem), `CONCLUIDA` (único reversível), `CANCELADA` e `DEVOLVIDA`
(terminais, garantidos por `UNIQUE (sale_id)` em `sale_reversals`).
SCRUM-227 e SCRUM-229 se resolvem sobre esses quatro — nenhum estado novo.

### Aritmética de desconto tem dono

`fn_register_sale_with_discounts` grava `sales.discount` como o desconto
TOTAL (itens + cabeçalho) e `sales.total` como o líquido; `original_total` é
coluna gerada (`total + discount`). Logo o comprovante reconcilia sem
recalcular nada:

    bruto           = original_total
    desconto itens  = Σ sale_items.discount_amount
    desconto venda  = discount − desconto itens
    total           = total

A validação dessa composição é de `calculate_discount_breakdown`
(`domain/sale_discount.py`), que já existe. O comprovante a reusa em vez de
abrir uma segunda redação da mesma conta.

### O que realmente falta

1. Os dados da empresa. Nada no aplicativo lê `company`; a `Session` carrega
   só `company_id`.
2. O objeto de domínio do comprovante e a regra de status para emiti-lo.
3. O layout e o gerador do documento.
4. A entrada na interface (emissão e reemissão).

## Decisões

### Formato: HTML na tela, PDF e impressão pelo PySide6

Um comprovante é documento de entrega ao cliente: precisa de layout, não de
tabela. `QTextBrowser` renderiza o HTML, `QPdfWriter` + `QTextDocument.print_`
grava o PDF e `QPrintDialog` imprime. Tudo vem do PySide6 já travado no
`uv.lock` — nenhuma dependência nova, que é o que o SCRUM-224 pede ao mandar
"avaliar o formato mais adequado às tecnologias existentes".

Rejeitado: CSV/TXT no padrão do US26. Serve para relatório tabular, não para
documento com cabeçalho de empresa, blocos e totais.

### Dados da empresa: leitura direta de `company`, sem migration

A policy `company_select` (`USING fn_is_member(id)`) e o `GRANT SELECT ... TO
app_backend, authenticated` existem desde `20261003120100_policies_security.sql`.
Ler `company.name` e `company.cnpj` pelo PostgREST é o caminho mais curto e
dispensa migration — o que importa porque migration pendente neste projeto
depende de aplicação manual no Supabase.

Rejeitado: `fn_get_company_profile` com migration (custo sem ganho; a policy
já faz o escopo). Rejeitado: levar o nome da empresa na `Session`
(`fn_my_companies` não devolve CNPJ).

### Sem registro de emissão

A US19 não pede histórico de comprovantes emitidos, e criar um seria regra de
negócio não solicitada. A reemissão regenera o documento a partir do snapshot;
nada é gravado em emissão nenhuma — que é como as regras 6 e 7 ficam
verdadeiras por construção, e não por disciplina.

### Venda cancelada emite comprovante marcado

A regra 5 exige que comprovantes de vendas canceladas indiquem o
cancelamento; a regra 1 exige confirmação para o comprovante definitivo.
Não há conflito: `CANCELADA`/`DEVOLVIDA` só são alcançáveis a partir de
`CONCLUIDA` (`fn_cancel_sale` recusa qualquer outro estado). Portanto:

| Status      | Emissão |
|---|---|
| `PENDENTE`  | recusada — a venda nunca foi confirmada |
| `CONCLUIDA` | comprovante válido |
| `CANCELADA` | emitido com faixa de cancelamento e motivo |
| `DEVOLVIDA` | emitido com faixa de devolução e motivo |

### Cliente: só o snapshot

`sales.client_name` é snapshot; `clients.document` não é. Ler o documento do
cadastro agora faria uma edição posterior do cliente alterar um comprovante
histórico — exatamente o que a regra 4 proíbe. O comprovante mostra o nome
gravado na venda. A regra 2 não lista documento do cliente entre os dados
obrigatórios, então nada se perde.

Os dados da empresa são caso diferente e por isso vêm do cadastro atual: a
empresa é a EMITENTE do documento, não uma grandeza comercial da operação.

## Arquitetura

Camadas na ordem em que o projeto já as usa.

### Domínio — `src/stockflow/domain/sale_receipt.py`

Sem Qt, sem I/O.

- `ReceiptCompany(name, document)`
- `ReceiptItem(code, name, quantity, unit_price, subtotal, discount, final_subtotal)`
- `ReceiptPayment(method, amount)`
- `ReceiptCancellation(kind, reason, when, by)`
- `SaleReceipt(sale_id, issued_on, company, client, seller, status, items,
  payment, gross, item_discount, sale_discount, total_discount, net,
  cancellation)` com `cancelado: bool`
- `ReceiptNotAvailable(ValueError)`
- `build_sale_receipt(venda: Mapping, company: ReceiptCompany) -> SaleReceipt`

`build_sale_receipt` é onde moram a recusa de `PENDENTE` e a composição dos
totais. Uma função, um lugar — a tela não repete a regra.

### Aplicação

`src/stockflow/application/ports/company_profile_repository.py`
: `CompanyProfileRepository` com `get_profile() -> ReceiptCompany`. Porta nova
  e estreita. A `CompanyRepository` existente não ganha método: ela é
  satisfeita hoje por `SupabaseProductRepository`, e acrescentar membro ao
  Protocol quebraria essa conformidade por fora do escopo desta história.

`src/stockflow/application/services/receipt_service.py`
: `ReceiptService.issue(session, sale_id) -> SaleReceipt`. Confere alçada de
  leitura de vendas, relê a venda pelo `SaleService`, busca a empresa e
  delega ao domínio. Nenhum método de escrita é alcançável daqui.

`src/stockflow/application/services/receipt_renderer.py`
: `render_receipt_html(receipt) -> str`, função pura. Irmã de
  `csv_exporter.py`: mesma camada, mesmo papel de serializar documento.

### Infraestrutura

- `repositories/supabase_company_repository.py` — lê `company` por
  `company_id`. `42501` vira indisponibilidade de dado da empresa, não falha
  de emissão.
- `repositories/demo_company_repository.py` — empresa do modo demonstração.
- `presentation/backend.py` — `build_company_repository(session)`, no mesmo
  formato dos demais `build_*`.

### Apresentação

- `widgets/sale_receipt_dialog.py` — `SaleReceiptDialog`: `QTextBrowser` com
  o HTML e os botões Salvar PDF / Imprimir / Fechar. Erro de gravação vira
  aviso na própria janela.
- `pages/sale_details.py` — botão "Emitir comprovante" e sinal
  `receipt_requested(str)`. Desabilitado com tooltip quando `PENDENTE`:
  cortesia visual, a recusa real é do serviço.
- `pages/vendas.py` — no feedback de venda gravada, o mesmo botão e o mesmo
  sinal, que é o "emitir após a confirmação" da história.
- `windows/main_window.py` — `_emitir_comprovante(sale_id)` relê pelo
  serviço, nunca pela linha da tabela (mesma razão já comentada em
  `_show_sale_details`: a linha é foto do momento da consulta).

## Fluxo

    [Vendas: venda gravada]  ou  [Detalhe da venda]
                 |                        |
                 +-----> receipt_requested(sale_id)
                                |
                 MainWindow._emitir_comprovante
                                |
                 ReceiptService.issue(session, sale_id)
                   | exigir_ver(session, "vendas", ...)
                   | SaleService.get_sale  -> fn_list_sales
                   | CompanyProfileRepository.get_profile -> company
                   +-> build_sale_receipt  -> SaleReceipt | ReceiptNotAvailable
                                |
                 render_receipt_html(receipt)
                                |
                 SaleReceiptDialog [ver | PDF | imprimir]

Tratamento de erro na janela: `PermissionDeniedError` → recusa de acesso;
`ReceiptNotAvailable` → informação ("venda não confirmada" / "venda não
disponível"); demais → aviso. Em nenhum ramo há escrita.

## Rastreio das regras de negócio

| Regra | Onde fica verdadeira |
|---|---|
| 1. Só venda confirmada gera comprovante definitivo | `build_sale_receipt` recusa `PENDENTE` |
| 2. Todos os dados obrigatórios | `SaleReceipt` + `render_receipt_html` |
| 3. Cliente quando associado | `SaleReceipt.client` é `None` sem nome gravado |
| 4. Reemissão preserva o original | snapshot de `sales`/`sale_items`; nada relido do cadastro |
| 5. Cancelamento visível | faixa e bloco de reversão no HTML |
| 6. Emissão não altera a venda | serviço sem caminho de escrita |
| 7. Falha não altera dado nem status | idem; renderização e PDF são posteriores à leitura |

## Testes

`tests/test_us19_comprovante_de_venda.py`, um caso por item do §6 da
história: emissão de venda confirmada; bloqueio de `PENDENTE`; integridade de
itens, preços e descontos; empresa e responsável; cliente associado e venda
sem cliente; pagamento; reemissão preservando o original depois de mexer no
cadastro de cliente e produto; comprovante de venda cancelada; falha durante a
geração; e ausência de alteração em venda, estoque e pagamentos.

Testes de interface em `tests/test_us19_comprovante_ui.py`: o botão no detalhe
e na tela de vendas, o estado desabilitado para `PENDENTE`, o conteúdo do
diálogo e a gravação do PDF em `tmp_path`.

## Fora de escopo

Nota fiscal eletrônica (`infrastructure/fiscal/nfe_client.py` é outro
assunto), envio do comprovante por e-mail, numeração sequencial de
comprovante, registro de emissões e qualquer alteração no fluxo de
cancelamento.
