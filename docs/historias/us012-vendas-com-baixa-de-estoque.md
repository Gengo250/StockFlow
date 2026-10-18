# US012 — Venda com itens e baixa automática de estoque

História
Como vendedor, quero registrar uma venda com seus itens e confirmar a operação com validação e baixa automática do estoque, para calcular corretamente o total e vender somente as quantidades disponíveis.

Critérios de aceite
A venda deve aceitar somente produtos ativos e quantidades válidas, recalculando subtotais e total automaticamente.

A confirmação deve ser bloqueada quando não houver itens ou quando qualquer produto possuir saldo insuficiente.

Ao confirmar, venda, itens, movimentações e baixa de estoque devem ser gravados atomicamente, sem permitir saldo negativo.

Cada item confirmado deve gerar uma SAÍDA_VENDA e o estoque deve refletir imediatamente a baixa, inclusive em vendas concorrentes.

=================================================
