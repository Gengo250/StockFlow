# Detalhes do evento — 06/11/2026

Acesso: entrar como ADMIN → Histórico de preços → selecionar um evento → **Ver detalhes do evento** (ou duplo clique). Voltar preserva filtros e seleção.

A consulta combina produto, usuário, período inclusivo, ação e entidade. A fonte existente fornece somente produtos e duas ações: alteração de preço de venda e alteração de custo. O filtro de entidade, portanto, oferece apenas Produto; não se trata de auditoria geral de operações. Autor está disponível por nome, sem identificador estável para distinguir homônimos.

Detalhe apresenta data/hora, usuário, ação, produto e valores anteriores/novos. Ausência não é zero. Campos são definidos explicitamente; nenhum payload bruto, senha, token ou atributo extra é renderizado. Textos do detalhe são literais, sem interpretação HTML. Não há comandos de edição/exclusão.

Permissão ADMIN existente preservada. Troca de sessão fecha detalhes, limpa registros e filtros; callbacks da sessão anterior são descartados. Não foram modificados serviços, repositórios, domínio, schema ou migrations. Nenhum acesso ao banco remoto foi feito.

## Validação

- **165 testes passaram em 39,97 s** na seleção final: 10 casos da nova UI, histórico H09, carregamento de páginas, serviço/repositórios de histórico, matriz de permissões, relatórios e aplicação demo.
- Cobertura inclui ausência de dados, acesso direto negado, resposta assíncrona de sessão antiga e preservação do usuário ao filtrar um produto sem eventos dele.
- Revisão independente: um problema de combinação de filtros encontrado e corrigido, com teste vermelho antes da correção e verde na seleção final.
- `git diff --check` sem erros.
- Capturas Qt offscreen revisadas: [consulta](historico.png) em 1024×768 e [detalhe](detalhes.png). Dados sintéticos.
- Não executada a suíte completa nesta rodada. Interface nativa e backend remoto não validados.

12ui foi consultado, mas não gerou referências: autenticação necessária e serviço de conexão indisponível. Implementação reutiliza o design system PySide6 existente.

Sem commit/push. Avaliação visual pelo usuário pendente.
