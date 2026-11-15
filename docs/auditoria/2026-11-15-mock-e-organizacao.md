# Verificação do mock e organização — 2026-11-15

Esta rodada usa a demonstração local; não executa integrações com PostgreSQL
nem acessa o Supabase. Os testes de infraestrutura que usam clientes falsos e
as verificações estáticas de SQL não comprovam comportamento de banco real.

## Aceite do mock

Suíte principal, com `QT_QPA_PLATFORM=offscreen`, backend `demo`, diretórios
de configuração/dados isolados em `/tmp` e bytecode desativado:

```bash
.venv/bin/python -m pytest tests/ --ignore=tests/integration \
  -k 'not supabase' -vv -p no:cacheprovider
```

Resultado: **1.753 passaram, 1 foi pulado e 120 foram excluídos pelo filtro**;
processo encerrado com código 0. O skip é o caso ADMIN da mudança de papel,
previsto no teste. O filtro também exclui testes de clientes Supabase falsos,
mas alguns testes locais de contratos estáticos e clientes falsos com outros
nomes continuam incluídos.

`tests/test_mock_application.py`: **6 passaram**. Inclui inicialização com
conexões bloqueadas, login, navegação, relatórios, estoque e cancelamento.
Cinco desses testes também estão no resultado da suíte principal; o teste de
inicialização é excluído ali por mencionar Supabase no nome.

Testes históricos adicionais foram executados separadamente com as fixtures de
`tests/conftest.py`:

```bash
QT_QPA_PLATFORM=offscreen STOCKFLOW_BACKEND=demo PYTHONPATH=tests:src \
  .venv/bin/python -m pytest -p conftest \
  docs/auditoria/2026-11-03/test_demo_review.py \
  docs/auditoria/2026-10-19/test_pending_remote_merge.py -q
```

Resultado: **7 passaram e 11 falharam**. Esses arquivos são testes históricos
de auditoria, fora da coleta normal, e alguns cenários pressupõem contratos de
uma versão anterior. As falhas não são prova de regressão recente.

O subconjunto local de `2026-10-05/test_acceptance.py` teve **15 aprovados e
5 selecionados para exclusão** (casos remotos ou de migration). O teste
independente `2026-11-02/test_acceptance_gaps.py::test_receipt_rejects_inconsistent_payment_total`
falhou, repetindo a mesma inconsistência de comprovante observada em 03/11.

Na auditoria de 03/11, persistem os cenários de saldo inicial sem movimento,
edição de produto que restaura saldo anterior após venda, venda cancelada após
fechamento do caixa, status de usuário inconsistente, último administrador
rebaixado, ordenação de vendas no mesmo dia e comprovante com total divergente.
O teste antigo de devolução chama um método com assinatura diferente da atual;
não comprova, por si só, que a falha original continua existindo. A análise e
o impacto originais estão no [relatório de 03/11](2026-11-03/README.md).

Na auditoria de 19/10 falharam os testes de abertura dos detalhes de
movimentação, filtro pelo autor e preservação do estoque máximo zero. É preciso
confrontar os dois primeiros com o fluxo atual e confirmar se zero continua
sendo valor distinto de ausência para o terceiro. Os três já estavam
documentados como pendentes no [relatório de 19/10](2026-10-19/README.md).

## Organização

O pytest procura testes em `tests/` por padrão. A documentação principal e de
testes aponta comandos para a demonstração; `docs/README.md` lista as áreas
ativas e os registros históricos. Caches comuns foram adicionados ao
`.gitignore`. Foram retirados da árvore quatro esqueletos com apenas README:
`assets/`, `src/stockflow/shared/`, `src/stockflow/infrastructure/config/` e
`src/stockflow/infrastructure/database/repositories/`. Os recursos e
repositórios efetivos permanecem em `presentation/assets/` e
`infrastructure/repositories/`.

Nesta execução, os READMEs removidos, 29 diretórios de cache Python, o cache
do pytest, `.DS_Store` e os intermediários de `build/` foram preservados em
`/tmp/stockflow-limpeza-BA8gB6/`. Esse diretório é temporário e pode ser
limpo pelo sistema. O executável anterior em `dist/` foi mantido.
