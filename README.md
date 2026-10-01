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
