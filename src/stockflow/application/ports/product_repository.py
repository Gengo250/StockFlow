"""Porta de persistência de produtos."""

from typing import Protocol

from stockflow.application.dto.product_input import ProductInput


class ProductRepository(Protocol):
    """Contrato que a infraestrutura deve satisfazer.

    Em uma implementação de banco, as verificações de status devem respeitar
    o escopo RLS da empresa e as gravações devem passar pelas funções
    autorizadas documentadas para o backend.
    """

    def exists(self, code: str) -> bool: ...

    def is_category_active(self, category: str) -> bool: ...

    def is_unit_active(self, unit: str) -> bool: ...

    def list_active_categories(self) -> tuple[str, ...]: ...

    def create_category(self, name: str) -> None:
        """Cadastra uma categoria na empresa da sessão.

        Está na porta porque sem ela uma empresa nova é um beco sem saída:
        o cadastro de produto exige categoria, e a única origem do combo era
        a leitura das categorias já existentes.
        """
        ...

    def list_active_units(self) -> tuple[str, ...]: ...
    def get(self, code: str):
        """Produto gravado sob o código, ou `None` se não houver.

        Devolver `None` em vez de levantar é deliberado: quem chama precisa
        distinguir ausência de inativo, e a distinção é da política (US02),
        não da persistência.
        """
        ...

    def list_all(self):
        """Catálogo inteiro, na ordem de cadastro — inativos inclusive.

        Filtrar aqui seria esconder o inativo também de quem precisa dele:
        a listagem do catálogo, a ficha do produto e a consulta de operações
        antigas.
        """
        ...

    def list_alerts(self) -> tuple:
        """Produtos em alerta de estoque baixo, pela regra da CONSULTA.

        Cada item é `(código, saldo, mínimo, situação)` — os quatro campos
        que a tela de alerta exibe.

        Existe para que a regra tenha um dono só. Enquanto a tela decidia
        sozinha quem alerta, havia duas implementações do mesmo critério; e
        a primeira vez que elas divergiram neste projeto, a divergência
        passou despercebida e violou um critério de aceitação.
        """
        ...

    def set_active(self, code: str, active: bool) -> None:
        """Ativa ou desativa o produto. Soft-delete, nunca remoção.

        Estava só no adaptador de banco e, por não estar aqui, ninguém o
        chamava: desativar pela tabela de Estoque mudava a tela e não
        persistia nada. Declarar na porta é o que torna a omissão visível.
        """
        ...

    def create(self, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...

    def update(self, code: str, data: ProductInput) -> str:
        """Retorna o code gravado."""
        ...
