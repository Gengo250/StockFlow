"""Cadastro da empresa emitente, lido direto de `public.company`.

Sem RPC nova: `company_select` (`USING fn_is_member(id)`) e o
`GRANT SELECT ... TO authenticated` existem desde
`20261003120100_policies_security.sql`. A RLS é quem escopa a leitura; o
`eq("id", ...)` só evita trazer as demais empresas do usuário.
"""

import logging

from stockflow.domain.sale_receipt import ReceiptCompany

logger = logging.getLogger("stockflow.company")

SEM_EMPRESA = ReceiptCompany(name="", document="")


class SupabaseCompanyRepository:
    def __init__(self, client, company_id):
        self._client, self._company_id = client, company_id

    def get_profile(self) -> ReceiptCompany:
        try:
            linhas = (
                self._client.table("company")
                .select("id,name,cnpj")
                .eq("id", self._company_id)
                .limit(1)
                .execute()
                .data
                or []
            )
        except Exception as erro:
            # Degradar, não derrubar: o comprovante é da VENDA, e o cabeçalho
            # da empresa é um bloco dele. `42501` aqui significa policy fora
            # do ar neste ambiente, e não venda inválida.
            logger.warning("Cadastro da empresa indisponível: %s", erro)
            return SEM_EMPRESA
        if not linhas:
            return SEM_EMPRESA
        return ReceiptCompany(
            name=str(linhas[0].get("name") or ""),
            document=str(linhas[0].get("cnpj") or ""),
        )
