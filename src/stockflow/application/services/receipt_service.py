"""Emissão e reemissão do comprovante de venda (US19/SCRUM-213).

Só de leitura, e isso é estrutural: este serviço conhece `get_sale` e
`get_profile`, e nenhum método que grave. É assim que as regras 6 e 7 da
história ficam verdadeiras por construção — uma falha aqui não tem como
alterar venda, estoque ou pagamento, porque não há o que chamar.
"""

from stockflow.domain.permissions import exigir_ver
from stockflow.domain.sale_receipt import (
    SEM_VENDA,
    ReceiptNotAvailable,
    build_sale_receipt,
)

SEM_IDENTIFICADOR = "Não foi possível identificar a venda."


class ReceiptService:
    def __init__(self, sales, companies):
        self._sales, self._companies = sales, companies

    def issue(self, session, sale_id):
        """Comprovante da venda, pelo MESMO caminho de leitura da US17.

        Emitir e reemitir são a mesma operação: não existe estado de "já
        emitido" para distinguir as duas, e inventar um seria o registro de
        emissões que a história não pede.
        """
        exigir_ver(session, "vendas", "emitir comprovante de venda")
        if not sale_id:
            raise ReceiptNotAvailable(SEM_IDENTIFICADOR)
        venda = self._sales.get_sale(session, sale_id)
        if venda is None:
            raise ReceiptNotAvailable(SEM_VENDA)
        return build_sale_receipt(venda, self._companies.get_profile())
