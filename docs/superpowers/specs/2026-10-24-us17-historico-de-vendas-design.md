# US17 — Consultar o histórico de vendas

Consulta paginada e filtrável das vendas registradas, tela de detalhe por
venda, e as operações de cancelamento e devolução que dão sentido ao estado
de cada uma.

Data: 2026-10-24

Cartões: SCRUM-212 (história), SCRUM-218 (consulta paginada), SCRUM-219
(filtros e ordenação), SCRUM-221 (detalhes da venda), SCRUM-222 (vínculos de
cancelamento e devolução), SCRUM-223 (bloqueio de edição).

## História

O usuário autorizado consulta as vendas registradas e seus detalhes, para
localizar operações, atender clientes e conferir informações comerciais. O
administrador cancela uma venda registrada por engano e registra a devolução
de uma venda cuja mercadoria voltou; nos dois casos o estoque acompanha e a
venda original continua no histórico, marcada.

## Estado antes desta história

A auditoria de 2026-10-24 apurou, com execução contra PostgreSQL real:

- A consulta ao histórico existe e é real (`SupabaseSaleRepository.list_all`),
  ordenada da mais recente para a mais antiga, escopada por empresa pela RLS.
- Não existe paginação em nenhuma camada. Com `max_rows = 1000` no PostgREST,
  a 1001ª venda desaparece sem aviso.
- Não existe nenhum dos filtros exigidos. Há uma única caixa de busca livre
  que filtra, em memória, as linhas já carregadas.
- Não existe tela de detalhe. O único detalhe é um tooltip na coluna Produto.
- Não existe cancelamento nem devolução de venda em nenhuma camada: sem
  estado `DEVOLVIDA`, sem tabela de vínculo, sem função, sem reversão de
  estoque. O enum tem `CANCELADA`, mas nada é capaz de atribuí-lo.
- O bloqueio de edição (SCRUM-223) já está entregue: `sales` e `sale_items`
  só têm `GRANT SELECT` e policies `FOR SELECT`, e a tela usa
  `NoEditTriggers`. Sondagem como `authenticated`: `UPDATE`, `DELETE` e
  `INSERT` recusados com `42501`.

Esta história preserva o SCRUM-223 e entrega os outros quatro.

## Critérios de aceitação

1. **Paginação real.** A consulta devolve uma página e o total de linhas. A
   navegação entre páginas não repete nem pula registro, em qualquer volume.
2. **Ordem cronológica.** A primeira página começa pela venda mais recente, e
   o empate de instante é desfeito de forma determinística.
3. **Filtros.** ID, período, cliente, vendedor e status, combináveis entre
   si, aplicados no banco, preservados ao paginar e ao recarregar.
4. **Ordenação.** O usuário escolhe entre critérios de uma lista fechada.
5. **Detalhes.** Uma tela por venda mostra itens, quantidades, preços
   unitários, subtotais, desconto, total, forma de pagamento, cliente e
   responsável.
6. **Cancelamento e devolução.** O `ADMIN` cancela ou devolve uma venda
   concluída, informando motivo obrigatório. O estoque acompanha. A venda
   original permanece no histórico.
7. **Vínculo visível.** O histórico distingue concluída, cancelada e
   devolvida, e o detalhe mostra o tipo, o motivo, o autor e a data da
   reversão, lidos do registro persistido.
8. **Edição continua bloqueada.** Nada nesta história abre caminho de escrita
   direta em `sales` ou `sale_items` para a aplicação.
9. **Permissões.** Consultar é de todos os papéis; reverter é só do `ADMIN`,
   recusado na aplicação e no banco de forma independente.

## Decisões de desenho

### A reversão é uma relação, não um atributo

O vínculo vive em `sale_reversals`, uma linha por reversão apontando para a
venda. As alternativas foram descartadas:

- **Colunas em `sales`** transformariam o vínculo em atributo. O cabeçalho
  engordaria a cada motivo novo, e não haveria onde registrar autoria
  separada da autoria da venda.
- **Reversão como venda nova de valor negativo** é fiel à realidade fiscal e
  caro demais: quebraria `CHECK (total >= 0)` e contaminaria toda consulta de
  venda com a pergunta "isto é venda ou estorno?".

A tabela repete um padrão que o projeto já tem. `sales_log` é exatamente
isso para a conclusão, e o comentário dela em `tables/06_clients_sales.sql`
já antecipa: *"sobrevive a uma reabertura ou cancelamento posterior"*.

### Cancelar e devolver movem o estoque por mecanismos diferentes

Os dois casos significam coisas diferentes, e o registro precisa preservar a
diferença:

- **Cancelamento** — a venda não deveria ter existido. As saídas dela passam
  a `CANCELADA`, e o trigger de recálculo que já existe devolve o saldo. É o
  padrão do projeto: *"cancelar uma confirmada devolve o saldo"*.
- **Devolução** — a venda aconteceu e a mercadoria voltou. Grava uma
  `ENTRADA` compensatória por item, vinculada à venda. A saída original
  continua `CONFIRMADA`, preservando que houve venda.

Nos dois casos o saldo muda **registrando movimentação, nunca escrevendo
`products.stock`**, como declara `triggers/06_sale_completion.sql`: quem
escrevesse o saldo direto seria sobrescrito pelo recálculo do trigger na
movimentação seguinte.

A reversão nasce na função da venda, e não em `fn_cancel_movement`, porque
esta recusa explicitamente cancelar uma saída vinculada a venda — regra da
US12 que esta história preserva.

### A reversão é terminal, e isso é regra de schema

`UNIQUE (sale_id)` em `sale_reversals`. Venda cancelada não vira devolvida
depois, nem acumula reversões. A regra também é conferida na função, mas o
índice é o que a torna verdadeira mesmo para quem chegue por outro caminho.

### Devolução é sempre total

Devolver a venda inteira. A devolução parcial exigiria tabela de itens
devolvidos, reversão por item, recálculo do total efetivo e um estado
intermediário de venda parcialmente devolvida — aproximadamente o dobro do
subsistema, espalhando regra por total, desconto e relatórios. Fica como
história futura se o uso pedir.

### Paginação e filtros no banco, não em memória

Uma função SQL recebe filtros, ordenação, limite e deslocamento, e devolve a
página junto com o total. A alternativa de paginar em memória é o padrão que
`MovimentacoesPage` usa hoje e teria o menor diff, mas não resolve o corte de
1000 linhas do PostgREST: o SCRUM-218 continuaria não atendido para volume
real. Concentrar a consulta numa função também evita que o repositório demo e
o do Supabase divirjam em semântica de filtro.

### Reverter é alçada do `ADMIN`, separada de vender

Registrar venda continua sendo `ADMIN` e `SELLER`. Desfazer é só do `ADMIN`.
Separar quem vende de quem reverte é o controle que o critério de permissões
pede; sem ele, o vendedor apaga o efeito da própria venda sem supervisão. A
área nova `vendas_reversao` entra na `PERMISSION_MATRIX` com
`fonte_gravar="fn_cancel_sale"`, para que o teste de espelhamento compare a
alçada declarada com a do SQL.

### Ação destrutiva mora no detalhe, não na listagem

Cancelar e devolver ficam dentro da tela de detalhe. Obrigar o administrador
a abrir a venda antes de revertê-la é justamente a distinção entre consultar
e operar que o SCRUM-223 pede, e tira a ação destrutiva de uma tabela densa
onde ela estaria a um clique de distância.

## Arquitetura

### Banco

`database/code/tables/06_clients_sales.sql`

```sql
ALTER TYPE public.sale_status ADD VALUE IF NOT EXISTS 'DEVOLVIDA';

CREATE TYPE public.sale_reversal_kind AS ENUM ('CANCELAMENTO', 'DEVOLUCAO');

CREATE TABLE public.sale_reversals (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id  uuid NOT NULL,
    sale_id     uuid NOT NULL,
    kind        public.sale_reversal_kind NOT NULL,
    reason      text NOT NULL CHECK (btrim(reason) <> ''),
    created_by  uuid,
    created_on  timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (company_id, sale_id)
        REFERENCES public.sales (company_id, id) ON DELETE CASCADE,
    UNIQUE (sale_id)
);
CREATE INDEX idx_sale_reversals_company ON public.sale_reversals (company_id);
```

`company_id` é duplicado de propósito, pela mesma razão de `sale_items`: a
policy escopa por coluna própria sem entrar em `sales` a cada linha.
`created_by` fica sem FK, como `sales.created_by`: a autoria precisa
sobreviver à remoção da conta.

`database/code/procedures/07_clients_sales.sql`

```sql
fn_list_sales(
    p_company_id uuid,
    p_sale_id    text               DEFAULT NULL,
    p_from       timestamptz        DEFAULT NULL,
    p_to         timestamptz        DEFAULT NULL,
    p_client_id  uuid               DEFAULT NULL,
    p_seller_id  uuid               DEFAULT NULL,
    p_status     public.sale_status DEFAULT NULL,
    p_sort       text               DEFAULT 'DATA_DESC',
    p_limit      integer            DEFAULT 50,
    p_offset     integer            DEFAULT 0
) RETURNS TABLE (
    id, client_id, client_name, seller_id, seller_name,
    payment_method, discount, total, status, created_on,
    items jsonb,
    reversal_kind, reversal_reason, reversal_on, reversal_by_name text,
    total_count bigint
) LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = public
```

Regras que decidem a corretude desta função:

- **Repete a checagem de `sales_select`.** `SECURITY DEFINER` passa por cima
  da RLS; sem `fn_is_member(p_company_id)` na entrada, a função vira a porta
  dos fundos do histórico. É a mesma lição já registrada em
  `fn_list_price_edits`.
- **`total_count` por `count(*) OVER ()`**, na mesma consulta. Uma segunda
  chamada de contagem poderia divergir da primeira sob concorrência, e a
  tela mostraria um número de páginas que não corresponde ao que lista.
- **Filtros por `(p_x IS NULL OR coluna = p_x)`**, combináveis. `p_sale_id`
  casa por prefixo do uuid em texto, que é como a tela exibe o ID.
- **`p_sort` resolvido por `CASE` sobre lista fechada**
  (`DATA_DESC`, `DATA_ASC`, `VALOR_DESC`, `VALOR_ASC`, `CLIENTE_ASC`), nunca
  por SQL dinâmico: texto do chamador virando `ORDER BY` é injeção.
- **Desempate sempre por `id`.** Duas vendas no mesmo instante têm ordem
  indefinida sem isso, e a página seguinte repetiria ou pularia linha.
- **Itens e reversão vêm na mesma leitura**, por agregação `jsonb` e
  `LEFT JOIN sale_reversals`. `LEFT JOIN` também em `user_accounts` para o
  nome do vendedor: linha de histórico que some porque a conta foi removida
  não é histórico.

```sql
fn_cancel_sale(p_sale_id uuid, p_reason text) RETURNS jsonb
fn_return_sale(p_sale_id uuid, p_reason text) RETURNS jsonb
```

Mesma espinha nas duas:

1. Lê a venda com `FOR UPDATE` e resolve `company_id` **da linha
   persistida**, nunca por parâmetro do chamador.
2. `fn_has_role(v_company, ARRAY['ADMIN'])`, senão `insufficient_privilege`.
3. Recusa status diferente de `CONCLUIDA` com `check_violation`.
4. Recusa motivo vazio com `check_violation`.
5. Grava a linha em `sale_reversals`.
6. Move o estoque pelo mecanismo da espécie (cancelamento anula as saídas;
   devolução grava entradas compensatórias com nota
   `DEVOLUCAO_VENDA - venda <id>`).
7. `UPDATE sales SET status = 'CANCELADA' | 'DEVOLVIDA'`.

`database/code/policies/01_security.sql`

- `ALTER TABLE public.sale_reversals ENABLE ROW LEVEL SECURITY`
- `GRANT SELECT` a `app_backend, authenticated`, e nada além. A escrita é
  exclusiva das funções `SECURITY DEFINER`, o que estende o SCRUM-223 à
  tabela nova.
- `CREATE POLICY sale_reversals_select ... USING (public.fn_is_member(company_id))`
- `fn_list_sales`, `fn_cancel_sale` e `fn_return_sale` entram na allowlist de
  `EXECUTE`. O bloco `RAISE EXCEPTION 'Funções obrigatórias ausentes'` no fim
  do arquivo é a rede: esquecer uma quebra a migration alto, em vez de deixar
  a aplicação sem permissão em runtime.

O schema é espelho triplo. Todo objeto novo precisa existir em
`database/code/`, na migration, e em `database/supabase/schemas/` como cópia
byte a byte — conferido por `test_code_cobre_todos_os_objetos_das_migrations`,
`test_code_nao_inventa_objetos_fora_das_migrations` e
`test_schemas_e_espelho_exato_de_code`. O espelho é gerado pelo sync, nunca
editado à mão.

A migration é escrita e verificada contra PostgreSQL local. **Quem aplica no
Supabase é o usuário.**

### Domínio e aplicação

| Arquivo | Conteúdo |
|---|---|
| `application/ports/sale_repository.py` | A porta que falta; vendas era o único domínio sem uma |
| `application/dto/sale_filter.py` | `SaleFilter` e `SalePage` congelados |
| `domain/enums/sale_status.py` | Espelho do enum do banco, com rótulos |
| `domain/enums/sale_reversal_kind.py` | `CANCELAMENTO` / `DEVOLUCAO`, com rótulos |

`domain/permissions.py` ganha:

```python
"vendas_reversao": Area(
    ver=TODOS_OS_PAPEIS,
    gravar=_ADMIN,
    fonte_ver="sales_select",
    fonte_gravar="fn_cancel_sale",
),
```

`SaleService`:

```python
def list_sales(self, session, filtro=None, page=1, size=50) -> SalePage
def get_sale(self, session, sale_id) -> dict
def cancel_sale(self, session, sale_id, reason)
def return_sale(self, session, sale_id, reason)
```

A guarda de permissão é a **primeira instrução** de cada método, antes de
qualquer acesso ao repositório — padrão aprovado neste projeto e provado por
teste de espião. A validação do motivo também acontece antes do repositório.

`list_sales` passa a exigir sessão, corrigindo a ausência de checagem
explícita apontada na auditoria.

### Adaptadores

`SupabaseSaleRepository` ganha `list_page`, `get`, `cancel` e `revert`, todos
por `rpc()`. `list_all()` permanece: Dashboard e Relatórios dependem dela.

`DemoSaleRepository` implementa a **mesma semântica** em memória — filtra,
ordena, pagina, devolve `total_count`, e a reversão mexe de verdade no
estoque demo. Se o demo mentir sobre a semântica, os testes de UI validam
ficção; é a lição registrada de que teste que fabrica o que o app não produz
não conta como prova.

Consequência declarada: ao introduzir `CANCELADA` e `DEVOLVIDA`, o Dashboard
e os Relatórios passariam a somar dinheiro de vendas revertidas. Os totais
monetários das duas telas passam a excluí-las. Não é escopo da US17, mas é
defeito que esta história criaria.

### Interface

`VendasPage`, card "Histórico de vendas":

- Filtros de ID, período (duas `QDateEdit` com presets de 7 e 30 dias, como
  Movimentações), cliente, vendedor e status, mais "Limpar filtros"
- Combo de ordenação
- Coluna **Status** com chip colorido, no molde de `movimentacoes.py`
- Controles de paginação reaproveitando o visual de
  `_create_pagination_controls`
- Botão de detalhe por linha
- Mudança de filtro volta para a página 1 e dispara a consulta pelo worker,
  nunca na thread da interface
- Filtros sobrevivem à paginação e à recarga

`SaleDetailsPage`, nova, na `PageStack`:

- Cabeçalho com ID, chip de status, data, cliente, vendedor e pagamento
- Tabela de itens com código, produto, quantidade, preço unitário e subtotal
- Totais: bruto, desconto, total
- Bloco de reversão quando existir: tipo, motivo, autor e data
- Ações **Cancelar venda** e **Registrar devolução**, só para `ADMIN` e só
  com status `CONCLUIDA`, cada uma pedindo motivo obrigatório
- Botão Voltar, como `ProductDetailsPage`

`MainWindow` registra a página, liga a navegação e o Voltar, e após uma
reversão reconsulta e atualiza Estoque, Produtos e Movimentações — a reversão
mexe no saldo, como já acontece no registro de venda.

## Tratamento de erro

| Situação | Tratamento |
|---|---|
| Reverter venda já revertida | `check_violation`; "Esta venda já foi cancelada/devolvida." |
| Não-`ADMIN` tentando reverter | Recusado na aplicação antes do banco; o banco recusa de novo com `insufficient_privilege` |
| Motivo vazio | Recusado no serviço; o repositório não é tocado |
| Devolução que estoura o estoque máximo | `trg_max_value_verify` pode recusar; a mensagem do banco é propagada |
| Falha de carga do histórico | Aviso na área da lista, não em diálogo — padrão já existente |

## Testes

| Arquivo | Cobre |
|---|---|
| `tests/unit/test_sale_permissions.py` | Espião: recusa não toca o repositório |
| `tests/test_us17_historico_de_vendas.py` | Filtros, combinação, paginação, filtros sobrevivendo à paginação, coluna de status, navegação ao detalhe |
| `tests/test_us17_reversao_de_venda.py` | Cancelar, devolver, efeito no estoque, terminalidade, alçada |
| `tests/test_schema_declarativo.py` | Seção US17, no molde de H09 e H11 |
| `tests/test_database_migrations.py` | Seção US17 |
| `scripts/verify_sales.py` | PostgreSQL real: paginação sem buraco nem repetição, filtros combinados, só `ADMIN` reverte, saldo volta, RLS em `sale_reversals`, reversão de venda de outra empresa recusada |

Teste antes do código. Verificação final: `pytest tests/` confrontado com o
baseline de **1074 passed, 27 skipped** apurado em 2026-10-24, mais
`scripts/verify_sales.py` contra PostgreSQL local descartável.

## Fora de escopo

- Devolução parcial
- Alterar `fn_cancel_movement`; a saída de venda continua não sendo
  cancelável isoladamente
- Corrigir `docs/auditoria/2026-10-05/test_acceptance.py`, deriva anterior a
  esta história
- Criar documento de backlog no repositório
- Aplicar a migration no Supabase
