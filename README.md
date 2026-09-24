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

A aplicação abre na tela de Dashboard. O menu lateral dá acesso a Estoque, Vendas, Produtos, Relatórios e Configurações.

## Estrutura

```
app/                                  ponto de entrada
└── __main__.py                       chama run()

src/stockflow/
└── presentation/                     camada de interface
    ├── app.py                        run(): cria o QApplication e abre a janela
    ├── windows/main_window.py        MainWindow: janela, menu lateral e páginas
    ├── widgets/sidebar.py            Sidebar
    ├── widgets/menu_button.py        botões do menu
    ├── styles/theme.py               folhas de estilo (QSS) da janela e da sidebar
    └── pages/                        telas: estoque, novo produto, em breve
```

As demais pastas (`src/stockflow/domain`, `application`, `infrastructure`, `shared`, além de `migrations`, `scripts`, `tests` e `assets`) estão reservadas para as próximas etapas — cada uma tem seu próprio README com a descrição e a equipe responsável.

## Comandos úteis

| Comando | O que faz |
|---|---|
| `uv sync` | recria o ambiente a partir do `uv.lock` |
| `uv add <pacote>` | adiciona uma dependência ao projeto |
| `uv run python -c "import stockflow"` | confere se o pacote está instalado |
