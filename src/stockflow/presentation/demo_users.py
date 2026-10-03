"""Base de usuários da demonstração.

Deriva de ``demo_data``, a mesma fonte que alimenta a tabela de Usuários e a
base de clientes de Vendas. Enquanto este módulo mantinha uma lista própria de
três pessoas, a tela exibia oito e o resumo contava outras três: cada tela
mostrava um total diferente da mesma base.
"""

from stockflow.presentation.demo_data import DEMO_PEOPLE, linhas_de_usuarios

# Linhas no contrato de demo_data:
# (nome, login, departamento, perfil, status, último acesso, cor)
DEMO_USERS = linhas_de_usuarios()

# Perfis realmente presentes na base, na ordem em que aparecem.
USER_ROLES = tuple(dict.fromkeys(person.role for person in DEMO_PEOPLE))
