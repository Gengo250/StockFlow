# Interface unificada — 23/10/2026

Direção aprovada: manter menu azul escuro, modernizar e unificar o conteúdo.
Implementação local em `newUItest`, baseada em `06c8c9b`; sem publicação.

## O que mudou

- Paleta neutra e tokens compartilhados em `presentation/styles/design_system.py`.
- Tipografia, superfícies, campos, botões, tabelas, foco, seleção e estados consistentes.
- Marca StockFlow no menu, preservando destinos e permissões.
- Revisão das 11 páginas, detalhes, login, recuperação e formulários de produto, categoria, cliente, fornecedor e usuário.
- Labels acima dos campos nos diálogos; ação principal à direita.
- Linhas de estoque compactas, números alinhados, nomes legíveis com rolagem horizontal e situações coloridas com rótulos.
- Nenhuma alteração em domínio, serviços, adaptadores, autenticação ou SQL.

Referências: [ERPNext](https://docs.frappe.io/framework/user/en/desk/navigation/workspace), [Frappe UI](https://ui.frappe.io/), [Odoo Inventory](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/reporting/dashboards.html).
O 12ui foi instalado e tentado, mas exigiu autenticação externa; não gerou proposta nem código. A implementação Qt segue a proposta aprovada e as referências pesquisadas.

## Conferência visual

- [Visão geral em 1440×900](previews/overview-1440.jpg)
- [Visão geral em 1024×768](previews/overview-1024.jpg)
- [Estoque antes/depois](previews/comparison-estoque.png)
- [Catálogo antes/depois](previews/comparison-produtos.png)

Capturei 63 estados antes e depois, em demonstração, com offscreen/Fusion.
O estado anterior foi reconstruído em `/tmp` a partir de `git archive HEAD` de `06c8c9b`, sem trocar a branch ou sobrescrever arquivos locais. As capturas completas estão em `/tmp/stockflow-ui-comparison-before/` e `/tmp/stockflow-ui-final-20261023/`; são temporárias. Prévias selecionadas foram preservadas neste diretório.

Para reproduzir as capturas do código atual:

```bash
uv run python docs/ui/2026-10-23/capture.py /tmp/stockflow-ui-review
```

Os screenshots não comprovam aparência no compositor nativo, outras fontes ou escalas DPI. O aviso `QLayout::addChildLayout` já aparece na versão anterior; não foi introduzido pelo tema. O script usa o objeto de catálogo na edição para contornar o erro preexistente de tupla de oito campos, sem corrigi-lo.

## Verificações

- Geometria, foco e indicador dos seletores: **5 passed**. Os testes reproduziram falhas antes das correções.
- Primeira seleção de navegação/permissões/relatórios: **97 passed, 1 skipped**.
- Seleção final de navegação, login, formulários, usuários, vendas e geometria: **107 passed**.
- Último acabamento dos diálogos e máscaras: **56 passed**.
- Suíte completa: **1076 passed, 27 skipped em 505,70 s**, exit code 0. Esse processo começou antes dos três últimos testes novos e dos ajustes finais de foco/seta/coluna/diálogos. As seleções finais acima verificaram esses ajustes; não foi repetida toda a suíte após eles.
- Conferência final de geometria + domínio/permissões/contratos SQL: **253 passed em 0,55 s**.
- Os 27 skips cobrem integração sem PostgreSQL local configurado e um caso condicional da matriz de permissões (ADMIN já alcança todas as áreas); não significam validação de banco remoto.
- Auditoria preexistente: **4 failed, 3 passed**; detalhes sem navegação, autor no filtro, máximo zero e tupla de estoque. Mesmas falhas documentadas antes da repaginação.
- Revisão independente apontou foco primário, seta do combo e coluna de produto em janela pequena. As três questões foram corrigidas e cobertas pelos testes de renderização.
- Limite menor preservado: a barra superior identifica a área de trabalho; não exibe breadcrumb dinâmico por página.

## Testar a interface nativa

Na raiz do repositório:

```bash
uv sync --frozen
STOCKFLOW_BACKEND=demo uv run stockflow
```

Esse modo usa demonstração local. A tela de login apresenta o acesso demonstrativo. Não definir `QT_QPA_PLATFORM=offscreen` ao abrir a janela para inspeção manual.


Comandos de verificação (prefixo comum: `QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_STYLE_OVERRIDE=Fusion`):

```bash
.venv/bin/python -m pytest tests/ -q --tb=short
.venv/bin/python -m pytest tests/test_ui_content_bounds.py tests/test_window_viewport.py tests/test_login.py tests/test_product_details.py tests/test_cadastro_de_categoria.py tests/test_clientes_us07.py tests/test_client_input_masks.py tests/test_fornecedores_us08.py tests/test_sales_checkout_regression.py tests/test_usuarios_do_banco.py -q --tb=short
.venv/bin/python -m pytest tests/test_clientes_us07.py tests/test_fornecedores_us08.py tests/test_client_input_masks.py tests/test_ui_content_bounds.py -q --tb=short
```

A suíte principal não inclui `docs/auditoria/2026-10-19/test_pending_remote_merge.py`. O resultado verde não resolve aquelas quatro falhas preexistentes. Build e interface nativa continuam dependentes de validação própria; o pedido atual entrega o código local para inspeção manual.
