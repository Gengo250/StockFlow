# Auditoria do StockFlow — 05/10/2026

**Veredito: não está tudo funcionando e não é possível afirmar que todas as alterações da interface chegam ao Supabase.** A suíte existente passa, mas não cobre várias lacunas de aceite. O login remoto funciona; a janela principal atual não abre com o banco real por incompatibilidade de schema.

Esta rodada é uma auditoria. Não modifica o código de produção, não aplica migrations e não implementa as funcionalidades faltantes.

## Resultados executados

| Verificação | Resultado | O que comprova |
|---|---|---|
| Suíte original `pytest tests/` | **518 passaram**, 0 falhas, 0 ignorados; 38 s | Comportamentos já cobertos pelos testes locais, incluindo widgets Qt, domínio, contratos dos adaptadores, compilador e análise estática de SQL |
| Aceite adicional dirigido pelas lacunas | **20 casos: 18 falharam, 2 passaram**; 6,45 s | Reproduções de funcionalidades incompletas e regras divergentes; dois controles positivos de movimentação e permissões |
| Verificação autenticada real | **14 checagens: 5 passaram, 9 falharam** | Login como ADMIN, leitura de tabelas existentes, diretório de usuários e incompatibilidades reais da API |
| Diagnóstico anônimo ampliado | 15 objetos consultados | Bloqueio anônimo nos objetos existentes consultáveis; tabelas/funções/colunas novas ausentes |
| Capturas Qt offscreen | 36 imagens produzidas | Navegação e renderização em duas dimensões solicitadas; sete amostras preservadas aqui |
| Espelho declarativo | 23 arquivos SQL idênticos | `database/code/` corresponde a `database/supabase/schemas/`; isso não prova que as 40 migrations executam |

As 18 falhas adicionais são **casos de teste**, não 18 defeitos independentes: há três valores inválidos para a mesma falha de venda e duas views afetadas pela mesma migration. Não foram usados `skip` ou `xfail` para esconder falhas.

## Bloqueios confirmados no Supabase

A conta de teste fornecida autenticou pelos campos e botão reais de `LoginWindow` e recebeu papel **ADMIN**. Credenciais, tokens, URL e conteúdo das linhas reais não foram registrados nas evidências.

| Operação real | Resultado |
|---|---|
| Login pela UI | PASS |
| Ler `categories` | PASS |
| Ler `products` sem a coluna nova | PASS |
| Ler `stock_movements` sem a coluna nova | PASS |
| Executar `fn_list_company_users` | PASS |
| Ler `products` com o contrato atual | `42703`: `products.supplier_id` não existe |
| Ler `stock_movements` com o contrato atual | `42703`: `stock_movements.supplier_id` não existe |
| Ler `suppliers`, `clients` e `sales` | `PGRST205`: não encontradas no schema cache |
| Executar `fn_list_company_suppliers` e `fn_list_company_clients` | `PGRST202`: não encontradas no schema cache |
| Ler `vw_stock_alerts.product_code` | `42703`: coluna não existe |
| Construir `MainWindow` com os adaptadores reais | **Falha em `products.supplier_id`** |

Os objetos ausentes correspondem às mudanças de `20261004160000_alert_view_carries_barcode.sql`, `20261004170000_clients_sales.sql` e `20261004180000_supplier_management.sql`. A API comprova que esses contratos não estão disponíveis. Não foi possível consultar o histórico administrativo das migrations: a CLI exige um access token que não está configurado. Portanto, não se presume um histórico de aplicação completo apenas a partir dessas ausências.

**Nenhum cadastro ou movimento de auditoria chegou a ser criado.** O roteiro parou ao abrir a janela, antes das etapas de escrita. O login teve seus efeitos normais no Auth, e a sessão de teste foi encerrada explicitamente pelo roteiro. Não há registros de produto/fornecedor/movimento para limpar.

## Achados priorizados

### 1. Bloqueante — aplicativo e banco incompatíveis

`SupabaseProductRepository._products_query()` solicita `supplier_id` em toda leitura. Como a coluna não existe no remoto, `build_catalog()` falha durante a construção da janela. Não se trata de senha errada: o login e a resolução de empresa/papel passaram.

Evidência: [resultado autenticado](remote-authenticated.json), [repositório de produtos](../../../src/stockflow/infrastructure/repositories/supabase_product_repository.py), [montagem da janela](../../../src/stockflow/presentation/windows/main_window.py).

### 2. Bloqueante de implantação — migration de views incompatível com `OR REPLACE`

Na migration `20261004150000`, a terceira coluna das views é `product_name`. A `20261004160000` insere `product_code` nessa posição e desloca as demais. PostgreSQL exige preservar nome, ordem e tipo das colunas existentes em `CREATE OR REPLACE VIEW`; colunas novas podem ser acrescentadas ao final. Essa regra foi conferida na [documentação oficial do PostgreSQL 17](https://www.postgresql.org/docs/17/sql-createview.html).

Os dois testes `test_view_migration_preserves_existing_column_prefix` reproduzem **estaticamente** a incompatibilidade. Não houve execução da migration num Postgres local: não há executáveis PostgreSQL disponíveis e o daemon Docker está desligado. A evidência permite apontar o contrato inválido, mas não substituir uma execução integral das migrations.

Providência: revisar essa migration e manter a fonte declarativa e seus espelhos coerentes antes da aplicação. Verificar também a `20261004150000`: ela converte mínimos existentes iguais a zero para `NULL`, portanto não deve ser reaplicada indiscriminadamente.

Evidência: [migration de alertas](../../../database/supabase/migrations/20261004160000_alert_view_carries_barcode.sql), [migration anterior](../../../database/supabase/migrations/20261004150000_minimum_stock_optional.sql).

### 3. Alta — Clientes e Vendas não persistem no backend Supabase

`MainWindow` sempre constrói `ClientesPage`, que instancia `DemoClientRepository`. O `backend.build_client_directory()` declara o backend Supabase como não implementado e nem é usado para montar essa página.

`VendasPage` mantém o histórico numa lista Python, registra com `historico_vendas.insert(...)` e não chama `fn_register_sale`. O teste com a composição real da janela em modo Supabase e cliente HTTP falso registra **zero RPCs de venda**. Reiniciar o aplicativo descarta essas vendas e os novos clientes da página.

Aplicar as migrations de clientes e vendas, sozinho, não conecta essas telas ao banco.

Evidência: [clientes](../../../src/stockflow/presentation/pages/clientes.py), [vendas](../../../src/stockflow/presentation/pages/vendas.py), [backend](../../../src/stockflow/presentation/backend.py); testes `test_remote_clients_use_persistent_repository` e `test_remote_sale_reaches_rpc`.

### 4. Alta — troca de empresa reaproveita repositórios e dados anteriores

`LoginFlow.open_main()` reaproveita a janela e chama `apply_session()`. Isso muda a sessão e os controles, mas não recria os repositórios de produtos, movimentações e fornecedores com o novo `company_id`, nem descarta o catálogo anterior.

A reprodução entra com empresa A, sai e entra com empresa B: a sessão é B e o repositório continua A. Isso comprova retenção indevida do contexto/cache no cliente; **não comprova contorno da RLS do servidor**. A RLS pode recusar consultas posteriores, enquanto a UI ainda guarda dados da sessão anterior.

Além disso, `LoginFlow.logout()` apenas esconde a janela e limpa o formulário; não chama `auth.sign_out()`. O roteiro de auditoria encerrou sua própria sessão explicitamente, mas o fluxo normal do aplicativo não faz isso.

Evidência: [fluxo de login/logout](../../../src/stockflow/presentation/app.py), `MainWindow.apply_session`; testes `test_relogin_rebuilds_company_repositories` e `test_logout_ends_supabase_session`.

### 5. Alta — regras de venda e cliente incompletas

- Venda aceita `abc`, `-10,00` e `NaN` como valor e adiciona linha ao histórico.
- Produto é revalidado antes da venda; cliente selecionado não é revalidado. Se for inativado depois de montar o combo, a seleção antiga ainda registra venda.
- STOCK consegue registrar venda e recebe botão de cadastro de clientes habilitado. O SQL de clientes/vendas permite escrita somente a ADMIN e SELLER; `ClientService` não recebe sessão nem faz essa guarda.
- Cliente criado pelo formulário aparece na manutenção, mas não entra na seleção de Vendas. `_sync_sales_page()` reconstrói a lista a partir de `DEMO_PEOPLE`, ignorando os clientes novos e os nomes editados.

Evidência: testes de valores inválidos, cliente inativo, papel STOCK e cadastro real por diálogo em [test_acceptance.py](test_acceptance.py); [serviço de clientes](../../../src/stockflow/application/services/client_service.py) e [regras SQL de clientes/vendas](../../../database/code/procedures/07_clients_sales.sql).

### 6. Alta — movimentações divergem das regras anunciadas

- Selecionar produto em Movimentações, inativá-lo em Estoque e então registrar ainda gera movimento. O combo permanece com a seleção antiga, `MovementService.register()` não revalida produto ativo e `fn_register_movement()` só verifica existência/empresa.
- Na demonstração, confirmar saída superior ao saldo produz saldo negativo. No SQL do repositório, `products` tem `CHECK (stock >= 0)`, e o trigger deve recusar a operação. Há um teste original verde que exige saldo negativo (`test_saldo_pode_ficar_negativo`) com comentário incorreto dizendo que o banco faz o mesmo.

O ciclo normal pendente → confirmada → cancelada e a propagação do saldo passaram nos testes locais. A divergência é nos limites e nas recusas. A restrição de saldo no remoto não foi exercitada com escrita nesta rodada, pois a janela não abriu.

Evidência: [serviço](../../../src/stockflow/application/services/movement_service.py), [adaptador demo](../../../src/stockflow/infrastructure/repositories/demo_movement_repository.py), [tabela real declarada](../../../database/code/tables/03_catalog.sql), [função SQL](../../../database/code/procedures/04a_movements.sql).

### 7. Média — tratamento de erro e campos prometidos sem persistência

- `_save_new_product()` e `_save_edited_product()` não capturam falhas gerais de rede/API. Um `RuntimeError` simulado escapa do handler, em vez de produzir estado de erro controlado. O teste não simula uma escrita remota bem-sucedida; ele verifica o tratamento da falha.
- A descrição preenchida no produto desaparece ao reabrir a edição. `ProductInput` e o modelo persistido também não transportam NCM, EAN separado, localização ou a opção visual de aviso de estoque baixo. Esses campos existem no formulário, mas não têm persistência correspondente.

Evidência: teste `test_product_save_handles_connection_error`, teste `test_optional_product_fields_survive_reopen`, [DTO](../../../src/stockflow/application/dto/product_input.py), [coleta do formulário](../../../src/stockflow/presentation/pages/novo_produto.py).

### 8. Funcionalidades ainda não entregues

Inspeção do código e das telas confirmou:

- Cadastrar e editar usuários: formulário abre, mas salvar permanece desabilitado inclusive para ADMIN. Listagem e ativação/inativação são caminhos separados; a listagem foi validada no remoto.
- Dashboard: página vazia.
- Relatórios e Configurações: `ComingSoonPage`.
- Salvar rascunho de produto: botão sem handler.
- Imagem de produto: apresentação sem fluxo de upload/persistência.
- Busca rápida e notificações na barra superior: sem integração, declaradas como “em breve”.
- Recuperação de acesso por e-mail: ainda indisponível.

Esses itens são lacunas de implementação, não necessariamente regressões. Sem o backlog formal/cartões completos no repositório, não é possível declarar que cada um era obrigatório nesta entrega; é possível afirmar que a funcionalidade visível não está concluída.

## Matriz de funcionalidades

| Área | Interface/regras locais | Integração persistente atual | Validação remota desta rodada |
|---|---|---|---|
| Login | Testes de login, campos e papéis passam | Supabase Auth + resolução de empresa/papel | **PASS**, ADMIN |
| Produtos / US01 | Cadastro/edição dos campos principais passam; campos opcionais acima não persistem | Adaptador RPC implementado | **Bloqueado** pela coluna `supplier_id` ausente |
| Ativo/inativo / US02 | Catálogo e seleção de vendas cobertos | RPC de status implementada | Escrita não alcançada; lacuna em movimentações |
| Estoque / US03 | Consulta, busca e estados da lista cobertos | Catálogo e movimentações implementados | Contrato atual de leitura falha |
| Alertas / US04 | Casos de mínimo, filtros e ordenação cobertos | View consultada pelo adaptador | **Falha**: `product_code` ausente |
| Permissões / US05 | Produto, usuário, fornecedor e movimento têm testes de recusa | Funções e RLS declaradas | Um papel ADMIN e bloqueios anônimos verificados; outros papéis/tenants não autenticados |
| Movimentações / US06 | Ciclo normal passa; duas divergências de regra acima | RPCs e trigger declarados | Leitura atual falha por `supplier_id`; escrita não alcançada |
| Clientes / US07 | CRUD demo; integração com Vendas e permissões incompletas | **Adaptador persistente ausente** | Tabela/função ausentes na API |
| Fornecedores / US08 | CRUD e validações locais passam | Adaptador RPC implementado | Tabela/função/colunas ausentes na API |
| Vendas | Simulação em memória; validações incompletas | **Sem chamada de persistência** | Tabela ausente na API |
| Usuários | Consulta/status com testes; cadastro/edição incompletos | Listagem/status implementados | Listagem passou; não foi alterado usuário existente |
| Dashboard, Relatórios, Configurações | Vazio/placeholders | Ausente | Não aplicável |

## Evidências e reprodução

Executar os comandos a partir da raiz do repositório, com o ambiente já instalado:

```bash
# Linha de base original, sem coletar os diagnósticos de rede.
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q

# Casos adicionais de aceite: atualmente termina com 18 falhas e 2 sucessos.
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest docs/auditoria/2026-10-05/test_acceptance.py -q --tb=short

# Somente leitura anônima do remoto, usando a configuração local.
.venv/bin/python docs/auditoria/2026-10-05/probe_remote.py

# Capturas da demonstração; não precisa de credenciais.
QT_QPA_PLATFORM=offscreen STOCKFLOW_BACKEND=demo .venv/bin/python scripts/check_visual.py /tmp/stockflow-capturas
```

O roteiro [live_acceptance.py](live_acceptance.py) pede e-mail e senha com entrada oculta. Ele contém etapas de escrita para um teste futuro com schema compatível: cria somente registros marcados `__AUDIT_...`, cancela suas movimentações e inativa os cadastros ao final. **Na execução registrada aqui, nenhuma etapa de escrita foi alcançada**. Os resultados são gravados em `/tmp/stockflow-audit-20261005`, sem credenciais. Não o executar contra uma conta diferente sem conferir o destino e a finalidade de teste.

Arquivos de evidência:

- [baseline.xml](baseline.xml): 518 testes originais.
- [acceptance.xml](acceptance.xml) e [acceptance.log](acceptance.log): resultados e falhas adicionais.
- [remote-authenticated.json](remote-authenticated.json): erros exatos e verificações reais.
- [remote-anonymous.json](remote-anonymous.json): consultas anônimas ampliadas.
- [screenshots](screenshots/): amostras visuais de dados demonstrativos.

As capturas não foram comparadas com uma baseline visual aprovada. O texto “0 differences” do script sem `--baseline` não significa ausência de defeitos visuais. Algumas telas aumentam a largura mínima efetiva; o prefixo `1024` no nome indica a dimensão solicitada pelo roteiro, não garante largura final de 1024 pixels.

Os testes adicionais usam widgets reais e, em dois fluxos de composição, cliente Supabase falso para provar a ausência de chamadas ou o reaproveitamento do tenant. Isso não equivale a um servidor PostgreSQL. A confirmação do banco remoto está nos JSONs separados.

## Próxima sequência técnica

1. Corrigir o contrato da migration de views e validar as migrations em PostgreSQL isolado; conferir histórico remoto e a conversão de mínimos antes de aplicar.
2. Disponibilizar no remoto o schema exigido pelo aplicativo, com autorização para essa mudança de implantação.
3. Conectar Clientes/Vendas aos repositórios/RPCs e implementar as permissões de ADMIN/SELLER.
4. Recriar contexto/repositórios por sessão, limpar caches e encerrar sessão no logout.
5. Corrigir as regras de limite e revalidação de movimentações/vendas e o tratamento de falhas de gravação.
6. Decidir quais campos/botões incompletos fazem parte da entrega e concluir ou sinalizar seu estado na UI.
7. Reexecutar os casos adicionais e o ciclo **interface → gravação → nova consulta independente → limpeza dos dados de teste**, com papéis e empresas de teste distintos.

Nenhuma cobertura percentual foi inventada, e o sucesso dos 518 testes não foi tratado como prova de completude funcional.

---

# Fechamento — correções aplicadas

Rodada posterior à auditoria, no mesmo repositório. Os achados acima ficam como o estado **antes** das correções; esta seção registra o que mudou e com qual evidência.

## Resultado atual

| Verificação | Antes | Agora |
|---|---|---|
| `pytest tests/` | 518 passaram | **565 passaram**, 0 falhas |
| Aceite da auditoria (`test_acceptance.py`) | 18 falhas / 2 sucessos | **20 passaram** |
| `scripts/verify_postgres.py` (41 migrations em PostgreSQL 18 isolado) | não executado — sem binários | **26 verificações, todas PASS** |
| `scripts/verify_postgres.py --schema` (25 arquivos de `database/code`) | não executado | **26 verificações, todas PASS** |

As verificações em PostgreSQL executam a janela Qt real contra o banco e **releem por uma conexão independente** — é o ciclo interface → gravação → nova consulta que a auditoria pedia, agora possível porque o schema local corresponde ao código.

## Achados fechados

| # | Achado | Correção |
|---|---|---|
| 1 | App e banco incompatíveis (`products.supplier_id`) | Schema alinhado ao contrato do adaptador; falta **aplicar no remoto** (abaixo) |
| 2 | Migration de views incompatível com `OR REPLACE` | `vw_stock_alerts` passou a receber `product_code` **ao final**; confirmado em banco real e em aplicação incremental |
| 3 | Clientes e Vendas sem persistência | `SupabaseClientRepository` e `SupabaseSaleRepository` ligados pela `MainWindow`; `fn_register_sale` comprovado por RPC no fake e por gravação real no PostgreSQL local |
| 4 | Troca de empresa reaproveitava repositórios | Repositórios recriados por sessão; `logout` encerra a sessão Auth |
| 5 | Regras de venda e cliente incompletas | Valor validado, cliente revalidado, permissões ADMIN/SELLER no serviço, cliente novo entra na seleção de Vendas |
| 6 | Movimentações divergiam das regras | Produto revalidado no registro; saldo negativo recusado também na demonstração, como o `CHECK (stock >= 0)` faz |
| 7 | Erros de rede e campos sem persistência | Falhas de gravação tratadas; descrição, NCM, EAN, localização, aviso de mínimo e imagem persistem |
| 8 | Funcionalidades não entregues | Dashboard, Relatórios, Configurações, rascunho de produto, busca rápida, notificações, imagem de produto, cadastro/edição de usuário e recuperação de acesso implementados |

## Correções desta rodada (continuação)

1. **Seleção de cliente perdida na navegação.** Entrar em Vendas ressincroniza a lista de clientes, e a recarga descartava o cliente escolhido pelo carrinho da tela de Usuários. `recarregar_clientes_disponiveis()` passou a reapontar a escolha, como o combo de produtos já fazia, e `_associar_cliente_e_abrir_vendas` navega antes de selecionar.
2. **Perfis da demonstração fora do enum do banco.** "Gerente", "Operador" e "Financeiro" não existem em `public.user_role`: editar essas pessoas abria o formulário num perfil que não era o delas e salvar só poderia falhar no banco. A base demonstrativa passou a usar os três papéis reais.
3. **Tela inicial divergente do menu.** A preferência nascia em "estoque" enquanto a sidebar marcava `DEFAULT_KEY`; a janela abria numa tela com o menu apontando para outra.
4. **Dois gatilhos para a regra do último administrador.** `trg_preserve_last_admin` duplicava `trg_company_users_keep_admin`, com mensagem e SQLSTATE diferentes para a mesma recusa. Sobrou um gatilho, que ganhou o `FOR UPDATE` serializando duas portas de administração concorrentes.
5. **`products.supplier_id` declarada duas vezes** em `database/code` (no `CREATE TABLE` e num `ALTER ADD COLUMN`): o schema declarativo não construía em banco limpo.

As invariantes dessas cinco correções estão fixadas em `tests/test_audit_regression.py`.

## Pendência única: aplicar no remoto

O código está pronto; o Supabase remoto ainda **não** tem o schema. Sondagem somente-leitura desta rodada:

```
products / stock_movements / vw_stock_alerts : 42703 (coluna ausente)
clients / sales / suppliers                  : PGRST205 (tabela ausente)
fn_list_company_clients / _suppliers         : PGRST202 (função ausente)
```

Faltam 4 migrations: `20261004160000`, `20261004170000`, `20261004180000` e `20261005120000`.

A aplicação foi ensaiada localmente a partir de **três estados possíveis do remoto** (cortes em `20261004140000`, `150000` e `170000`). Nos três, as pendentes aplicam na ordem, `vw_stock_alerts` ganha `product_code` ao final e um produto preexistente sobrevive intacto, recebendo os campos novos com os defaults:

```
('PRD-ANTIGO', 'Produto antigo', 7, None, '', '', '', '', True)
```

Comando para aplicar — **a ser executado por você**, que detém a credencial administrativa:

```bash
cd database
supabase link --project-ref "$SUPABASE_PROJECT_REF"   # exige o access token da CLI
supabase db push                                      # aplica as 4 migrations pendentes
```

Depois da aplicação, repetir o ciclo contra o remoto:

```bash
.venv/bin/python docs/auditoria/2026-10-05/probe_remote.py     # as 15 consultas devem parar de acusar ausência
.venv/bin/python docs/auditoria/2026-10-05/live_acceptance.py  # login real, gravação, releitura e limpeza
```

## Pós-aplicação das migrations

`supabase db push` aplicou as 4 migrations pendentes. O roteiro real passou a avançar muito além do ponto anterior: leitura autenticada de `products`, `categories`, `stock_movements`, `suppliers`, `clients` e `sales`, as três funções de listagem, `vw_stock_alerts` com `product_code`, **abertura da janela principal com repositórios reais** e **cadastro de fornecedor pela interface com releitura do banco** — todos PASS.

Parou num único ponto, e ele expôs um defeito que nenhuma migration resolveria:

### 9. Alta — empresa nova não conseguia cadastrar o primeiro produto

`fn_create_categories` existe no banco desde o início, mas **nada no aplicativo a chamava**. O combo de categoria do formulário só era preenchido por leitura das categorias já existentes. Numa empresa recém-criada ele vinha com o placeholder e mais nada — e como o cadastro de produto exige categoria, o primeiro produto era impossível de registrar pela tela. O impasse era invisível na demonstração, que nasce com categorias prontas.

Correção: o formulário de produto (cadastro e edição) ganhou o botão **Nova** ao lado do combo. Ele pede o nome, chama `ProductService.create_category`, reconsulta as categorias da empresa e já deixa a nova selecionada, preservando o resto do formulário. A permissão segue a mesma regra de `fn_create_categories` — só ADMIN e STOCK — verificada no serviço, no botão e no banco.

Evidência: `tests/test_cadastro_de_categoria.py` (15 casos) e, em PostgreSQL real, as três verificações novas de `scripts/verify_postgres.py`:

```
PASS Company without categories offers none
PASS Qt creates the first category of the company
PASS Category persisted and reread independently
```

O verificador deixou de semear a categoria por SQL: ele agora cria a primeira **pela interface**, no mesmo estado de empresa vazia que travou o aceite real.

### Estado final verificado

| Verificação | Resultado |
|---|---|
| `pytest tests/` | **562 passaram** |
| `pytest tests/ docs/auditoria/2026-10-05/test_acceptance.py` | **582 passaram** |
| `scripts/verify_postgres.py` (41 migrations) | **29/29 PASS** |
| `scripts/verify_postgres.py --schema` (`database/code`) | **29/29 PASS** |

`live_acceptance.py` também cria a primeira categoria pela interface quando a empresa não tem nenhuma. **Atenção:** a categoria criada permanece no banco — o aplicativo não remove categoria, e a limpeza do roteiro informa o `DELETE` a rodar no SQL Editor caso você queira apagá-la.
