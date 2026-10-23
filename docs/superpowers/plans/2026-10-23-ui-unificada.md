# Interface unificada Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Renovar as páginas Qt preservando o menu azul escuro e os fluxos existentes.

**Architecture:** Tokens e funções de QSS em `presentation/styles/design_system.py`; módulos de estilo públicos delegam a essa base. Componentes e páginas usam os mesmos tokens, cabeçalhos e geometrias, sem stylesheet global sobrepor cores semânticas.

**Tech Stack:** Python 3.12, PySide6, qtawesome, pytest.

**Spec:** `docs/superpowers/specs/2026-10-23-ui-unificada-design.md`, aprovada pelo usuário em 23/10.

## Global Constraints

- Manter PySide6 e menu azul escuro; português e marca StockFlow.
- Fundo #F6F8FB, superfícies #FFFFFF, borda #E2E8F0, primária #2563EB.
- Nenhuma alteração em banco, permissões ou serviços; sem dependência de runtime nova.
- Fluxos, sinais e campos preservados; regressões antigas registradas separadamente.
- Executar na branch de UI `newUItest` existente e no caminho indicado pelo usuário para facilitar teste local. Sem commit/push automático.

## Review Focus

- Largura 1024: conteúdo e ações continuam acessíveis com rolagem.
- Cores semânticas: badges, erro, seleção e desabilitado legíveis.
- Diálogos e login: controles visíveis e marca coerente.
- Estados vazios/carregando/falha continuam distintos.
- Tabelas: cabeçalhos e ações sem cortes nas resoluções previstas.

### Task 1: Sistema visual e shell

**Files:** criar `styles/design_system.py`; modificar `styles/theme.py`, `inventory.py`, `widgets/form_fields.py`, `sidebar.py`, `top_bar.py`, `menu_button.py`.

**Interfaces:** produzir tokens e `page_qss`, `surface_qss`, `button_qss`, `field_qss`, `table_qss`, `directory_qss`, `page_layout`, `status_badge_qss`. Preservar constantes existentes para consumidores.

- [x] Conferir referências/capturas e tentar 12ui; registrar indisponibilidade se houver.
- [x] Implementar tokens e QSS compartilhados com foco, desabilitado e erro.
- [x] Atualizar menu/marca e barra superior com contexto de página.
- [x] Validar visual e testes existentes de navegação/permissões.

### Task 2: Aplicação nas páginas e formulários

**Files:** `styles/{clients,suppliers,users,products,login}.py`; `pages/*.py` ativas; `widgets/{product_form,product_card,stock_table,user_table,user_summary,category_form,password_recovery}.py`; `windows/login_window.py`, `windows/main_window.py` apenas apresentação.

**Interfaces:** consumir tokens e QSS de Task 1; manter contratos públicos e sinais existentes.

- [x] Migrar estilos e geometrias para a base compartilhada; eliminar estilos concorrentes nas páginas.
- [x] Padronizar tabelas, cards, cabeçalhos, contagens, filtros, forms e estados.
- [x] Verificar os fluxos atuais com os testes existentes, sem testes que espelhem cores/literais.
- [x] Ajustar geometria somente quando captura ou teste demonstrar necessidade.

### Task 3: Verificação e entrega

**Files:** capturas e registro de validação em `docs/ui/2026-10-23/`; documentação e vault.

**Interfaces:** captura offscreen/Fusion em 1440×900 e 1024×768 das páginas e formulários; registro dos limites de verificação.

- [x] Executar suíte em `tests/` com ambiente Qt controlado, registrar resultado completo.
- [x] Executar reproduções antigas separadamente e comparar com 4 falhas conhecidas.
- [x] Inspecionar capturas antes/depois de todas as páginas, login e formulários.
- [x] Revisão independente final, corrigir regressões relevantes e verificar.
- [x] Atualizar cérebro e entregar comando `cd /home/luccas/Projects/StockFlow && uv run stockflow`.

## Execução

Usuário aprovou e pediu implementar nesta sessão. Não há outra rodada de aprovação. Mudanças visuais reversíveis serão verificadas por renderização e testes existentes; não criar testes de valores QSS que apenas repitam a implementação.


## Registro de execução

- Task 1 completa: tokens, shell e estilos; validação inicial 97 passed/1 skipped. 12ui instalado, mas geração indisponível sem autenticação. Aplicada a proposta aprovada em Qt.
- Task 2 completa: 11 páginas e formulários migrados; testes específicos finais 107 passed e 56 passed.
- Task 3 completa: 63 estados capturados antes e depois; revisão independente concluída; três achados importantes corrigidos com testes RED→GREEN; documentação e memória atualizadas.
- Verificação final: suíte 1076 passed/27 skipped antes do último acabamento; seleções finais e 253 testes de geometria/domínio/SQL verdes depois dele. Evidências e limites em `docs/ui/2026-10-23/README.md`.
- Decisão: trabalhar na branch de UI existente no caminho autorizado, sem worktree adicional ou commit, para o usuário testar nesse diretório.
- Decisão: verificar mudanças puramente visuais com capturas e testes existentes; novos testes apenas para falhas concretas de geometria/acessibilidade reproduzidas.
- Decisão: preservar as quatro regressões anteriores fora do escopo visual, conforme a proposta aprovada.
- Pendência menor: breadcrumb dinâmico; a barra superior usa identificação fixa da área de trabalho.
- Entrega local, sem merge, push, release, alterações no Supabase ou build.
