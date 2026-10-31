"""Empresa emitente no modo demonstração."""

from stockflow.domain.sale_receipt import ReceiptCompany

#: CNPJ válido pelos dígitos verificadores e declaradamente de exemplo. Um
#: número inventado faria o comprovante da demonstração passar por documento
#: de uma empresa real.
EMPRESA_DEMO = ReceiptCompany(
    name="StockFlow Comércio LTDA (demonstração)",
    document="11222333000181",
)


class DemoCompanyRepository:
    def get_profile(self) -> ReceiptCompany:
        return EMPRESA_DEMO
