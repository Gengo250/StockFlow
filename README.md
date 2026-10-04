# StockFlow

Sistema de gerenciamento de estoque em desktop, construído com PySide6.

Nota: cada arquivo README.md tem descrição e a divisão de equipes que vão trabalhar no projeto, isso é somente uma versão de teste e ao longo do projeto terão mudanças

## Requisitos

- [uv](https://docs.astral.sh/uv/) — gerencia o Python, o ambiente virtual e as dependências
- Python 3.12 (o uv baixa sozinho se você não tiver; a versão está fixada em `.python-version`)

Não é preciso criar venv na mão nem rodar `pip install`.

## Instalação

Na raiz do projeto:

```bash
uv sync
```

Esse comando cria o `.venv/` e instala as dependências travadas no `uv.lock` (PySide6 e qtawesome).

## Como rodar

Duas formas equivalentes:

```bash
uv run stockflow
```

```bash
uv run python app
```

A aplicação sempre abre na tela de login. A conta local de demonstração é
`ana.ferreira@example.com`, com senha `StockFlow123`. Após entrar, o Dashboard
dá acesso ao menu de Estoque, Vendas, Produtos, Relatórios e Configurações.
O botão de sair no rodapé do menu retorna ao login e limpa a senha.
“Lembrar e-mail” guarda apenas o e-mail nas configurações locais, sem pular o login.
Este acesso demonstrativo não substitui autenticação de produção: não há servidor,
cadastro de credenciais ou recuperação por e-mail nesta versão.

Em **Produtos**, busque um item e clique no card do produto. A tela mostra identificador, nome, categoria, unidade, preço
de venda, custo e status ativo/inativo. **Voltar para produtos** preserva a busca.
Se o item não estiver mais disponível, uma mensagem orienta o retorno à listagem.
Por padrão o catálogo usa dados demonstrativos locais, compartilhados com o
estoque em `presentation/demo_products.py`. Para gravar no Supabase, veja
**Backend de banco** abaixo.

Em **Estoque** (US03), a tabela mostra **saldo, mínimo e situação** de cada
produto, e a busca localiza por código, nome ou categoria. A situação NÃO é um
valor gravado: vem de `domain/stock_level.py`, que é **tradução literal de
`public.fn_stock_state`** e é recalculada a cada redesenho.

| Situação | Regra |
|---|---|
| — | mínimo ausente ou zero: sem limiar configurado, não alerta |
| `Crítico` | saldo zerado |
| `Baixo` | saldo **menor ou igual** ao mínimo |
| `Atenção` | acima do mínimo, mas a menos de 20% dele |
| `Normal` | o resto |

O filtro **`Abaixo do mínimo`** é a consulta da US04 em um clique: produtos
ativos, com mínimo configurado, cujo saldo é menor ou igual a esse mínimo —
ordenados do mais urgente para o menos. Quem não tem mínimo definido fica de
fora, por isso a coluna mostra `—` em vez de `0`. No banco a mesma consulta é
a view `vw_stock_alerts`.

A regra tem um dono só, e é o banco: enquanto a UI teve regra própria, ela
divergia de `fn_stock_state` em 5 de 11 casos — a tela dizia `Crítico` onde um
relatório SQL dizia `Baixo`, e produto sem mínimo aparecia no alerta.

O botão de ação da linha **desativa** o produto (soft-delete, como
`fn_set_product_active`); ele some da lista e só reaparece em `Inativos`, de
onde pode ser reativado.

Em **Vendas**, uma venda nova escolhe cliente, produto e valor. A lista de
produtos oferece apenas os que estão **ativos**: desativar um item no Estoque
(ou pelo formulário de edição) o retira da seleção na hora, e a gravação
revalida a situação antes de registrar — a lista é uma foto, e o produto pode
ser desativado com a tela de Vendas aberta. O **histórico** não muda: cada
venda guarda o produto que foi associado a ela, então operações antigas
continuam exibindo o item original mesmo depois de ele ser desativado ou sair
do catálogo.

A mesma regra vale para compras e movimentações operacionais quando essas
telas existirem: a situação do produto tem um dono só,
`domain/product_status.py`, consultado pelos módulos através de
`application/services/product_selection_service.py`.

## Testes

Para validar navegação, detalhes, formulários, filtros e grade responsiva sem
abrir uma janela:

```bash
QT_QPA_PLATFORM=offscreen uv run --with pytest python -m pytest tests/ -q
```

Sempre com o caminho `tests/`: `pytest` sem argumento varre `scripts/` e tenta
coletar `scripts/test_supabase_connection.py`, que fala com a rede.

## Backend de banco

A aplicação roda em **demonstração por padrão** — catálogo em memória, contas
locais, nenhuma rede. Para gravar no Supabase:

```bash
STOCKFLOW_BACKEND=supabase uv run stockflow
```

O opt-in é explícito, e não "usa banco se houver `.env`": o `.env` deste
repositório existe para os scripts de verificação, e deduzir intenção dele
faria a aplicação exigir rede numa máquina onde isso não foi pedido.

Antes do primeiro login com o banco, três passos — nesta ordem:

1. **Aplique as migrations** `20261003180000_auth_jwt_identity.sql` (identidade
   por JWT e permissões) e `20261004090000_user_directory.sql` (departamento e
   último acesso na tela de Usuários). Sem a primeira, `fn_current_user_id()`
   só lê a variável de sessão `app.user_id`, que um cliente REST não tem como
   definir, e `anon`/`authenticated` não têm privilégio nenhum — toda chamada
   responde `permission denied`.
2. **Crie os usuários no Supabase Auth** (painel ou `auth.admin`).
3. **Vincule e autorize cada conta**: `user_accounts.auth_user_id` apontando
   para o Auth, e uma linha em `company_users` com empresa e papel. O roteiro
   pronto, com diagnóstico do que falta, está em
   `scripts/provisionar_usuario.sql`. Sem o vínculo o login falha com mensagem
   própria, dizendo exatamente isso.

O que muda com o backend ligado: o login passa a ser `sign_in_with_password`,
a empresa e o papel vêm de `fn_my_companies`, e toda gravação vai por função
`SECURITY DEFINER` (`fn_create_products`, `fn_update_products`,
`fn_set_product_active`, `fn_set_min_stock`) — as tabelas não têm `GRANT` de
INSERT/UPDATE para nenhuma role de aplicação.

O **saldo** não é um número digitado: é a soma das **movimentações
confirmadas** (`stock_movements`). `fn_create_products` e `fn_update_products`
não escrevem `products.stock` — registram movimentação, e um trigger recalcula
a coluna a partir das linhas com situação `CONFIRMADA`. Movimentação nasce
`PENDENTE`: registrar não é confirmar, e só confirmar muda o saldo.

Em **Usuários**, a lista vem de `fn_list_company_users`, que recusa quem não é
ADMIN. A busca só acontece ao abrir a tela, não ao montar a janela: um papel
sem permissão nem chega a gastar a requisição. Três colunas são derivadas, não
lidas — perfil (`user_role` traduzido), status e último acesso:

| Status | Significa |
|---|---|
| `Ativo` | `company_users.active` e já entrou pelo menos uma vez |
| `Pendente` | acesso liberado, mas `auth.users.last_sign_in_at` é nulo |
| `Inativo` | `company_users.active = false` |

Um usuário com nome em minúsculo e sem e-mail é uma conta de domínio que ainda
não foi vinculada ao Supabase Auth — ela aparece de propósito, porque é
justamente a que precisa de providência.

## Estrutura

```
app/                                  ponto de entrada
└── __main__.py                       chama run()

src/stockflow/
├── domain/                           regras que não dependem de tela nem de banco
│   ├── permissions.py                quem pode cadastrar/editar produto e usuário
│   ├── product_status.py             produto ativo/inativo em operações novas
│   ├── stock_level.py                espelho de fn_stock_state (US03/US04)
│   ├── enums/                        papéis de usuário e tipos de operação
│   └── exceptions/                   recusas nomeadas do domínio
├── application/                      casos de uso sobre o domínio
│   ├── services/product_service.py           cadastro e edição de produto
│   ├── services/product_selection_service.py seleção de produto por compras,
│   │                                         vendas e movimentações
│   ├── ports/                        contratos que a infraestrutura satisfaz
│   └── dto/                          dados como a UI os entrega
├── infrastructure/                   adaptadores de persistência
│   ├── auth/supabase_auth.py                 login pelo Supabase Auth -> Session
│   ├── database/supabase_client.py           cliente preguiçoso, criado sob demanda
│   ├── repositories/demo_product_repository.py   catálogo em memória
│   ├── repositories/product_mapper.py        tradução catálogo <-> public.products
│   ├── repositories/supabase_product_repository.py  catálogo no Supabase
│   ├── repositories/user_mapper.py           linha de usuário <-> tupla da tela
│   └── repositories/supabase_user_repository.py     diretório de usuários
└── presentation/                     camada de interface
    ├── app.py                        run(): cria o QApplication e abre a janela
    ├── backend.py                    escolhe demonstração ou banco
    ├── windows/main_window.py        MainWindow: janela, menu lateral e páginas
    ├── demo_products.py              produtos demonstrativos compartilhados
    ├── demo_users.py                 usuários demonstrativos e perfis
    ├── widgets/                      componentes visuais reutilizáveis
    │   ├── stock_table.py            tabela e ações do estoque
    │   ├── form_fields.py            campos e estrutura comum dos cards
    │   ├── product_form.py           seções do formulário de produto
    │   ├── product_card.py           card do catálogo
    │   └── ...                       sidebar, barra superior e usuários
    ├── styles/                       QSS da janela, estoque, produtos e usuários
    └── pages/                        composição das telas
```

As pastas `shared`, `migrations` e `assets` seguem reservadas para as próximas etapas — cada uma tem seu próprio README com a descrição e a equipe responsável.

## Executável desktop (beta)

### Baixar pronto

O executável de cada versão fica publicado em
[Releases](https://github.com/Gengo250/StockFlow/releases). Não é preciso ter
Python, uv nem clonar o repositório — só baixar e rodar.

```bash
# Linux x64
chmod +x StockFlow-0.1.0-linux-x64
./StockFlow-0.1.0-linux-x64
```

| Plataforma | Arquivo | Estado |
|---|---|---|
| Linux x64 | `StockFlow-<versão>-linux-x64` | beta, validado |
| Windows x64 | `StockFlow-<versão>-windows-x64.exe` | a receita suporta, ainda não publicado |

O arquivo não é assinado. No Linux, lembre do `chmod +x`; no Windows, o
SmartScreen pode pedir "Mais informações → Executar assim mesmo".

### Gerar localmente

Gera um arquivo único, sem precisar de Python instalado na máquina de destino:

```bash
uv run python scripts/build_desktop.py
```

O resultado sai em `dist/`, nomeado por versão e plataforma — por exemplo
`dist/StockFlow-0.1.0-linux-x64`. Basta dar duplo clique ou executar direto.

| Flag | O que faz |
|---|---|
| (nenhuma) | build + smoke test do executável gerado |
| `--no-smoke` | só compila, sem validar |
| `--keep-build` | mantém `build/`, deixando as próximas builds mais rápidas |

A receita fica em `packaging/stockflow.spec` e vale para Linux e Windows — o
mesmo comando roda nos dois sistemas. Hoje apenas o build Linux foi validado.

Dois pontos da receita que não são opcionais:

- as fontes do `qtawesome` são copiadas explicitamente; sem elas o app abre
  com a interface inteira sem ícones;
- os módulos Qt não usados (WebEngine, Qt3D, QML/Quick, Multimedia) são
  descartados, o que derruba o executável de mais de 300 MB para ~87 MB.

O primeiro frame demora alguns segundos: arquivo único é descompactado numa
pasta temporária a cada execução.

### Publicar uma release

A versão sai do `pyproject.toml` e vira o nome do arquivo e a tag. Fluxo
completo, partindo de um build validado:

```bash
# 1. build + smoke test (precisa terminar com "OK")
uv run python scripts/build_desktop.py

# 2. tag anotada apontando para o commit publicado
git tag -a v0.1.0-beta -m "StockFlow 0.1.0 beta - executavel desktop Linux"
git push origin v0.1.0-beta

# 3. release com o executável anexado
gh release create v0.1.0-beta dist/StockFlow-0.1.0-linux-x64 \
  --title "StockFlow v0.1.0-beta" \
  --notes-file docs/release-notes/v0.1.0-beta.md \
  --prerelease
```

Regras que valem para toda release:

- a tag segue `vMAJOR.MINOR.PATCH[-beta]` e acompanha o `version` do
  `pyproject.toml`;
- enquanto o app for beta, a release sai com `--prerelease`;
- `dist/` está no `.gitignore` de propósito: o binário vive na release, nunca
  no histórico do Git;
- cada plataforma entra como um anexo a mais na *mesma* release (o build
  Windows roda em uma máquina Windows e o `.exe` é anexado com
  `gh release upload v0.1.0-beta dist/StockFlow-0.1.0-windows-x64.exe`).

## Comandos úteis

| Comando | O que faz |
|---|---|
| `uv sync` | recria o ambiente a partir do `uv.lock` |
| `uv add <pacote>` | adiciona uma dependência ao projeto |
| `uv run python -c "import stockflow"` | confere se o pacote está instalado |

## Validação visual de refatorações

Antes de alterar a interface, capture as telas. Depois compare com a referência:

```bash
uv run python scripts/check_visual.py /tmp/stockflow-before
# Execute as alterações de código.
uv run python scripts/check_visual.py /tmp/stockflow-after --baseline /tmp/stockflow-before
```

O script compara pixels de 30 capturas em 1440×900 e 1024×768, incluindo páginas,
formulários e erro de carregamento. Use o mesmo ambiente, fontes e versão do Qt
nas duas execuções. Diferenças retornam código de saída diferente de zero.
As capturas usam o renderizador offscreen e o estilo Fusion; não substituem
uma inspeção no ambiente gráfico nativo.
