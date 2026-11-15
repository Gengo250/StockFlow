# Documentação e estrutura

- [README principal](../README.md): execução, modo de demonstração e arquitetura.
- [Testes](../tests/README.md): suíte local e integração com PostgreSQL.
- `auditoria/`: relatórios e evidências históricas de verificações.
- `historias/`: histórias de usuário.
- `release-notes/`: histórico de entregas.
- `superpowers/`: planos e especificações históricas.
- `ui/`: registros e capturas de interface.

O código executável fica em `src/stockflow/`: `domain/` contém regras de
negócio, `application/` os casos de uso, `infrastructure/` os adaptadores e
`presentation/` a interface PySide6. Os recursos visuais efetivamente usados
ficam em `presentation/assets/`, e os repositórios em
`infrastructure/repositories/`. A entrada alternativa é `app/__main__.py`.

`database/` contém o material do banco; `scripts/` reúne ferramentas de
desenvolvimento; `packaging/` mantém a configuração do empacotamento.
`build/` e `dist/` são gerados pelo empacotador e não são código-fonte.

Equipe responsável: Backend
