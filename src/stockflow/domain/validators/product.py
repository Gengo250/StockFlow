"""Validação dos dados obrigatórios para cadastro e edição de produtos."""

from decimal import Decimal, InvalidOperation
from typing import Callable, Protocol


class ProductValues(Protocol):
    code: str
    name: str
    category: str
    unit: str
    sale_price: str
    cost: str
    stock: str


def _texto_obrigatorio(valor, campo: str) -> str:
    texto = "" if valor is None else str(valor).strip()
    if not texto:
        obrigatorio = "obrigatória" if campo == "Unidade" else "obrigatório"
        raise ValueError(f"{campo} é {obrigatorio}.")
    return texto


def _valor_monetario(valor, campo: str) -> Decimal:
    texto = _texto_obrigatorio(valor, campo)
    texto = texto.replace("R$", "").replace(" ", "")

    # O formulário exibe a moeda no padrão brasileiro; também são aceitos
    # valores numéricos sem formatação para chamadas não originadas na UI.
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    try:
        numero = Decimal(texto)
    except InvalidOperation as erro:
        raise ValueError(f"{campo} deve ser um valor numérico válido.") from erro

    if not numero.is_finite():
        raise ValueError(f"{campo} deve ser um valor numérico válido.")
    if numero < 0:
        raise ValueError(f"{campo} não pode ser negativo.")
    return numero


def _validar_estoque(valor) -> None:
    if valor is None or not str(valor).strip():
        return
    try:
        quantidade = int(str(valor).strip())
    except ValueError as erro:
        raise ValueError("Estoque deve ser um número inteiro válido.") from erro
    if quantidade < 0:
        raise ValueError("Estoque não pode ser negativo.")


def validate_product(
    data: ProductValues,
    *,
    category_is_active: Callable[[str], bool],
    unit_is_active: Callable[[str], bool],
) -> None:
    """Recusa dados inválidos antes que o repositório grave o produto."""
    _texto_obrigatorio(data.code, "Identificador")
    _texto_obrigatorio(data.name, "Nome")
    category = _texto_obrigatorio(data.category, "Categoria")
    if category.lower() == "selecione uma categoria":
        raise ValueError("Categoria é obrigatória.")
    unit = _texto_obrigatorio(data.unit, "Unidade")
    _valor_monetario(data.sale_price, "Preço de venda")
    _valor_monetario(data.cost, "Custo")
    _validar_estoque(data.stock)

    if not category_is_active(category):
        raise ValueError(f"A categoria '{category}' está inativa ou indisponível.")
    if not unit_is_active(unit):
        raise ValueError(f"A unidade '{unit}' está inativa ou indisponível.")
