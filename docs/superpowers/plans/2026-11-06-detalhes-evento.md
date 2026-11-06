# Detalhes do evento — plano e decisões

Objetivo: consulta somente leitura de eventos disponíveis no histórico de preços/custos, em PySide6, sem alterações de backend ou SQL.

Escolha: ampliar HistoricoPrecosPage e abrir detalhe em diálogo não modal, preservando filtros e seleção. Uma nova página global de auditoria prometeria eventos que a fonte atual não fornece. ADMIN é a permissão existente; não criar papéis novos.

- [x] Testar filtros combinados (usuário, período inclusivo, ação, entidade/produto), ordem cronológica e período inválido.
- [x] Implementar filtros locais preservando o contrato de consulta por produto existente.
- [x] Implementar detalhes somente leitura com lista explícita de campos seguros, valores ausentes distintos de zero, textos sem HTML e sem payload bruto.
- [x] Negar abertura sem permissão, limpar dados/fechar diálogo na troca de sessão e ignorar retorno assíncrono antigo.
- [x] Verificar regressões de histórico/relatórios/permissões, revisar capturas e registrar limitações no vault.

Arquivos: presentation/pages/historico_precos.py, novo presentation/dialogs/audit_event_dialog.py, presentation/windows/main_window.py e tests/test_audit_event_details.py.

Limites: fonte atual só informa autor por nome, produto e mudança de preço/custo; não oferece ID do evento, IP, outras entidades nem eventos gerais. Não inventar estes dados. Segurança remota depende das políticas existentes e não será revalidada com acesso ao banco.
