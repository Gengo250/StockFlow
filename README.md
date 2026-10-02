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
O catálogo usa dados demonstrativos locais, compartilhados com o estoque em
`presentation/demo_products.py`; ainda não há integração com banco de dados.

Para validar navegação, detalhes, formulários, filtros e grade responsiva sem abrir uma janela:

```bash
uv run python -m unittest discover -s tests -v
```

## Estrutura

```
app/                                  ponto de entrada
└── __main__.py                       chama run()

src/stockflow/
└── presentation/                     camada de interface
    ├── app.py                        run(): cria o QApplication e abre a janela
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

As demais pastas (`src/stockflow/domain`, `application`, `infrastructure`, `shared`, além de `migrations` e `assets`) estão reservadas para as próximas etapas — cada uma tem seu próprio README com a descrição e a equipe responsável.

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
