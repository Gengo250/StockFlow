# StockFlow: interface unificada

Data: 23/10/2026. Estado: aprovada pelo usuário; implementação iniciada.

## Objetivo e direção escolhida

Modernizar a UI de todas as páginas e tornar navegação, tabelas, formulários e estados consistentes. O usuário escolheu **manter o menu azul escuro atual e modernizar o conteúdo**. Continuar com desktop PySide6, interface em português e operações existentes.

Foram consideradas três direções: ERP claro e compacto, menu azul escuro com conteúdo renovado, e tema escuro integral. A segunda foi escolhida pelo usuário; preserva a identidade de navegação enquanto permite uniformizar as áreas de trabalho. Tema escuro exigiria outra paleta de superfícies e estados; menu claro alteraria a identidade que o usuário decidiu manter.

## Referências pesquisadas

- ERPNext/Frappe Workspaces: https://docs.frappe.io/framework/user/en/desk/navigation/workspace — navegação persistente por módulos, indicadores e atalhos de operação.
- Frappe UI: https://ui.frappe.io/ — referência de componentes para cabeçalhos, navegação, campos, listas e badges. Usar a linguagem visual como inspiração; a implementação permanece em Qt.
- Odoo Inventory dashboards: https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/reporting/dashboards.html — indicadores voltados a estoque e operação. O mecanismo de busca retornou a documentação; a abertura integral da página expirou nesta sessão.

As decisões abaixo são propostas para StockFlow, não cópias das interfaces desses produtos.

## Diagnóstico local

O projeto distribui QSS entre `presentation/styles/`, componentes reutilizáveis e strings dentro das páginas. Os fundos azulados, bordas, alturas, cantos e espaçamentos variam; algumas telas usam cards e outras tabelas soltas. Já existem bases úteis em `styles/inventory.py` e `widgets/form_fields.py`, mas não cobrem todas as superfícies.

Capturas das 11 páginas em 1440×900: `/tmp/stockflow-ui-before-20261023/`. São referências temporárias anteriores à alteração, não entregáveis duráveis. Existe uma inconsistência de marca: a janela mostra “Atlas / Stock Management”, enquanto o projeto e a distribuição se chamam StockFlow. Proposta: exibir StockFlow / Gestão de estoque com o símbolo existente.

## Sistema visual proposto

| Elemento | Padrão |
| --- | --- |
| Menu | Azul escuro atual, mesmos destinos e permissões; seleção e hover mais discretos e ícones alinhados |
| Fundo de trabalho | Cinza muito claro `#F6F8FB` |
| Superfícies | Branco `#FFFFFF`, borda neutra `#E2E8F0`, sem gradientes decorativos |
| Texto principal / secundário | `#0F172A` / `#64748B` |
| Ação principal | Azul `#2563EB`, hover `#1D4ED8`, texto branco |
| Estados | Verde, âmbar e vermelho com texto explícito; cor não será o único indicador |
| Tipografia | Fonte sans disponível no sistema; escala comum: título 24 px, seção 16 px, corpo/campos 13–14 px, ajuda 12 px |
| Espaçamento | Base de 4 px; margens de página 24 px, intervalo entre seções 20 px, padding de cards 20 px |
| Controles | Altura de referência 40 px; foco visível, desabilitado e erro coerentes |
| Cantos | 8 px para controles, 12 px para cards; badges menores |
| Tabelas | Cabeçalho neutro, divisores suaves, seleção azul clara, números alinhados à direita quando apropriado; altura de linha de referência 48 px |

Tokens compartilhados e helpers Qt/QSS devem ser a fonte desses valores. Evitar substituições globais de cores ou stylesheet que sobrescreva cores semânticas de widgets filhos. Manter as constantes/imports públicos utilizados pelo restante do projeto ou migrar seus consumidores em conjunto.

## Composição e cobertura

Cada página terá cabeçalho com título e descrição, ação principal na posição previsível, faixa de busca/filtros e área de resultados. Formulários organizam dados em seções com labels acima dos campos; ações de salvar/cancelar seguem uma ordem comum. Ações secundárias usam botão neutro; exclusão/inativação continua distinguível.

- Dashboard: indicadores com a mesma composição; reposição em tabela e atualização com ação secundária.
- Estoque: busca e filtros alinhados; tabela dentro de superfície com contagem e estados de lista.
- Produtos: cards e grade com tipografia e ações da mesma família; criação, edição e detalhes usam os mesmos padrões de formulário.
- Movimentações: cadastro, ajuste, filtros e histórico com seções legíveis e espaçamento comum.
- Vendas: cliente, itens, totais e confirmação com hierarquia clara; histórico recebe o padrão comum de tabela/filtros.
- Clientes, fornecedores e usuários: listas e diálogos de cadastro/edição com componentes e ações equivalentes.
- Histórico de preços: filtros e tabela com o padrão comum, mantendo restrição de acesso.
- Relatórios: métricas, filtros, resultados e exportação consistentes com Dashboard e Estoque.
- Configurações: preferências com a mesma estrutura de seções e feedback.
- Login e recuperação de acesso: mesma marca, tipografia, campos, botões e feedback, adaptados à tela de entrada.
- Detalhes existentes, erros, vazio, carregamento e formulários modais também fazem parte da revisão visual. A página de detalhes de movimentação receberá o padrão visual, mas a integração de navegação quebrada permanece fora desta mudança.

## Limites e decisões de implementação

Preservar serviços, regras de saldo, autenticação, RPCs, migrations, permissões e contratos dos repositórios. Manter nomes de campos, sinais, navegação funcional e dados demonstrativos. As quatro regressões previamente reproduzidas serão referência do estado inicial e não serão tratadas como causadas pelo redesign. Se uma bloquear a captura, registrar e capturar por caminho alternativo; não ampliar a mudança para corrigir regras sem necessidade.

O implementador pode ajustar larguras, margens e espaçamentos por página quando a geometria real exigir. Não remover filtros/campos para fazer o layout caber. Em 1024×768, usar os mecanismos de rolagem existentes e permitir leitura e acesso às ações. Não exigir nova fonte, serviço remoto ou dependência em tempo de execução para o tema.

Ferramentas de design: explorar a direção selecionada com 12ui e adaptar a proposta aprovada para widgets Qt. Superdesign só pode complementar se suportar o contexto desktop e estiver disponível, sem substituir o app por HTML. Eventual autenticação, indisponibilidade ou resultado incompatível será comunicado. Não enviar `.env`, credenciais, dados reais de clientes nem repositório inteiro a serviços externos; usar capturas da demonstração e um resumo visual.

## Verificação e critério de conclusão

1. Capturar as 11 páginas e fluxos de formulário/login em 1440×900 e 1024×768 com offscreen/Fusion; comparar com o estado anterior e inspecionar visualmente.
2. Conferir consistência da paleta, textos, controles, tabelas, badges e estados. Sem texto recortado ou ações essenciais inacessíveis nos tamanhos previstos.
3. Executar testes existentes relevantes de navegação, permissões, viewport, formulários e relatórios. Rodar os contratos de domínio já aprovados para conferir preservação.
4. Identificar separadamente falhas anteriores e regressões novas. Não afirmar suíte completa verde com execução parcial.
5. Entregar código local, resumo de arquivos e testes, capturas antes/depois e atualização do cérebro. Sem push, release ou alterações no Supabase.

## Próxima etapa

Proposta aprovada pelo usuário. Implementar o plano `docs/superpowers/plans/2026-10-23-ui-unificada.md` e entregar instruções de execução local.
