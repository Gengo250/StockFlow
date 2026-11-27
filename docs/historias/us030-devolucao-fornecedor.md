# US30 — Devolver produtos ao fornecedor

Implementação de banco e backend na branch `US30`, no worktree
`/home/guiddc/stockflow/StockFlow-US30`. A base inclui a US18 (`4dae966`).
A branch `feat-us29-product-supplier` foi comparada: suas alterações são de
interface e não acrescentam dependências de banco ou backend para esta história.
O gateway permanece no worktree original, na branch `US18`.

## Comportamento

- `ADMIN` e `STOCK` podem registrar e consultar devoluções. O serviço exige
  identidade e empresa; as RPCs conferem novamente o vínculo ativo na empresa
  ativa. `SELLER`, anônimo, vínculo inativo e usuário de outra empresa são recusados.
- Fornecedor obrigatório; compra de origem opcional. Quando informada, a compra
  deve estar `RECEBIDA`, ser da mesma empresa e fornecedor e conter os produtos.
  O fornecedor principal cadastrado no produto não limita devoluções históricas.
- Cada item exige produto, quantidade inteira positiva e motivo de até 1000
  caracteres. Uma requisição aceita de 1 a 100 itens, até 1.000.000 de unidades
  por item. Linhas repetidas de um produto são somadas ao conferir o saldo.
- Produtos e fornecedores inativos podem participar de devolução de estoque
  existente. A inativação não impede corrigir um recebimento anterior.
- O limite de devolução é o saldo atual, conforme a história. A compra de origem
  é um vínculo de rastreabilidade; não foi acrescentado um limite acumulado por
  quantidade recebida naquela compra.
- Cada item gera uma `SAIDA` `CONFIRMADA`, com `supplier_return_id`,
  `supplier_return_item_id`, fornecedor, compra quando existente, motivo,
  responsável e data. **Nenhum enum de movimentação foi criado.**
- Cabeçalho e itens são imutáveis. Suas saídas não podem ser canceladas ou
  apagadas individualmente. O fluxo não cria cobrança nem reembolso.
- O banco trava os produtos antes da baixa. Cabeçalho, itens, saídas, saldo e
  evento crítico de auditoria são gravados na mesma transação; falha na auditoria
  também desfaz a operação. A auditoria registra saldo anterior e novo e os vínculos.
- A chave de idempotência é gerada no DTO. Reenviar o mesmo DTO/chave devolve o
  registro existente, sem nova baixa. Reutilizar a chave com outros dados ou outro
  responsável é recusado. Campos extras do JSON não são persistidos nem auditados.

## Uso pelo backend

```python
from stockflow.application.dto.supplier_return_input import (
    SupplierReturnInput, SupplierReturnItemInput,
)
from stockflow.presentation.backend import build_supplier_return_service

service = build_supplier_return_service(
    session, catalogo, supplier_repository, movement_repository, purchase_repository,
)
data = SupplierReturnInput(
    supplier_id=fornecedor_id,
    purchase_id=compra_id,  # None quando a origem não estiver disponível
    items=(SupplierReturnItemInput(codigo_produto, 2, "Produto avariado"),),
)
result = service.create_return(data)
history = service.list_returns(supplier_id=fornecedor_id, limit=50, offset=0)
details = service.get_return(result.return_id)
```

No Demo, reutilizar os repositórios já montados conserva o catálogo e o histórico
compartilhados. Esse modo mantém apenas estado em memória; a auditoria crítica
persistida faz parte da transação PostgreSQL. A interface não foi alterada.
No Supabase, o adaptador usa uma única RPC para gravar a operação; o responsável
vem da identidade autenticada no banco, não do payload do cliente.

RPCs públicas: `fn_register_supplier_return`, `fn_get_supplier_return` e
`fn_list_supplier_returns`. A função interna de montagem dos detalhes não é
concedida à aplicação. As tabelas possuem RLS e permitem somente leitura direta
aos papéis autorizados; a escrita passa pela RPC.

## Banco e validação

Migration nova: `database/supabase/migrations/20261127040500_us30_supplier_returns.sql`.
As fontes ficam em `database/code/{tables,procedures,triggers,policies}` e possuem
espelhos em `database/supabase/schemas`. Migrations anteriores foram preservadas.

Validação local em 27/11/2026:

- 1072 testes unitários e de contratos passaram.
- 423 testes de integração passaram em PostgreSQL 18 descartável, executando
  tanto o schema completo quanto a sequência de migrations.
- Cobertura da US30 inclui permissões, isolamento entre empresas, motivos,
  quantidades, vínculo da compra, histórico, auditoria, falha no segundo item,
  falha na auditoria, reenvio idempotente, concorrência real com duas conexões e
  upgrade sobre compras e movimentações já existentes.
- A suíte de integração também verifica regressões em compras, estoque, vendas,
  cancelamento, caixa e consulta de auditoria.

Comandos equivalentes após preparar o ambiente Python do worktree:

```bash
uv run pytest tests/unit tests/test_schema_declarativo.py tests/test_database_migrations.py tests/test_adapter_schema_contract.py -q
uv run pytest tests/integration -q
```

A execução de integração exige `STOCKFLOW_TEST_DSN` de um PostgreSQL **local**
no qual o executor possa criar e remover bancos descartáveis. Sem essa variável,
esses testes são ignorados. Os resultados acima vieram de um cluster temporário
isolado, encerrado após a execução. Não foi usado o banco remoto.

A migration não foi aplicada no Supabase, que continua indisponível.
Nenhum commit, push ou alteração de interface faz parte desta entrega.
