"""Porta de leitura do cadastro da empresa emitente (US19).

Porta NOVA e estreita em vez de um método a mais em `CompanyRepository`:
aquele contrato é satisfeito hoje pelo `SupabaseProductRepository`, e
acrescentar membro ao Protocol quebraria essa conformidade por fora do
escopo desta história.
"""

from typing import Protocol

from stockflow.domain.sale_receipt import ReceiptCompany


class CompanyProfileRepository(Protocol):
    def get_profile(self) -> ReceiptCompany:
        """Nome e documento da empresa da sessão.

        NÃO levanta quando o cadastro está indisponível: devolve uma empresa
        não identificada. O comprovante continua válido sem o cabeçalho, e
        perder o documento inteiro por causa de um bloco seria pior.
        """
        ...
