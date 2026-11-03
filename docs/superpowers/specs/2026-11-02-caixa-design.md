# Abertura e fechamento de caixa

Pedido: disponibilizar início e fechamento do caixa no aplicativo existente.
Decisão de implementação: botão Caixa em Vendas, com diálogo nativo e estilos existentes; evita acrescentar navegação para uma operação curta. Uma página exclusiva seria apropriada para histórico e sangrias, fora deste pedido.

ADMIN e SELLER podem abrir seu caixa com saldo inicial não negativo, recuperar a sessão ao reabrir o app e fechar declarando dinheiro, débito, crédito, Pix, vale e outros. Diferença exige justificativa. Erros mantêm os valores digitados. Operações remotas usam workers e impedem cliques duplicados.

O banco associa vendas à sessão aberta do operador autenticado, bloqueia abertura concorrente e valida empresa/operador. Um terminal é provisionado pela RPC ao abrir, sem pedir UUIDs ao usuário. Demo mantém estado em memória. Nenhuma migration remota será aplicada nesta tarefa; sua necessidade será documentada.
