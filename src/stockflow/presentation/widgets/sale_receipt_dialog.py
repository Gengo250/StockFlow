"""Entrega do comprovante: ver, salvar em PDF e imprimir (US19/SCRUM-224).

Nada aqui grava no banco. Erro de arquivo ou de impressora vira aviso na
própria janela — a venda já estava fechada antes de o diálogo abrir, e a
regra 7 da história exige que uma falha de geração não vá além dela.
"""

import qtawesome as qta
from PySide6.QtCore import QFile, QIODevice, QMarginsF, Qt
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)

from stockflow.application.services.receipt_renderer import render_receipt_html
from stockflow.presentation.styles import inventory

MARGEM_MM = 12


class SaleReceiptDialog(QDialog):
    def __init__(self, receipt, parent=None):
        super().__init__(parent)
        self.receipt = receipt
        self.html = render_receipt_html(receipt)
        self.setObjectName("saleReceiptDialog")
        self.setWindowTitle("Comprovante de venda")
        self.setMinimumSize(620, 640)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        self.viewer = QTextBrowser()
        self.viewer.setObjectName("saleReceiptViewer")
        self.viewer.setHtml(self.html)
        # Documento, não navegador: link clicável num comprovante abriria
        # caminho para fora do aplicativo sem nenhum ganho.
        self.viewer.setOpenExternalLinks(False)
        self.viewer.setOpenLinks(False)
        layout.addWidget(self.viewer, 1)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setVisible(False)
        layout.addWidget(self.status_label)

        layout.addLayout(self._criar_acoes())

    def _criar_acoes(self):
        linha = QHBoxLayout()
        linha.addStretch()
        self.pdf_button = QPushButton(" Salvar PDF")
        self.pdf_button.setIcon(qta.icon("fa5s.file-pdf", color="#B91C1C"))
        self.pdf_button.setAccessibleName("Salvar o comprovante em PDF")
        self.pdf_button.clicked.connect(self._escolher_destino)
        self.print_button = QPushButton(" Imprimir")
        self.print_button.setIcon(qta.icon("fa5s.print", color="#2563EB"))
        self.print_button.setAccessibleName("Imprimir o comprovante")
        self.print_button.clicked.connect(self._imprimir)
        self.close_button = QPushButton("Fechar")
        self.close_button.setAccessibleName("Fechar o comprovante")
        self.close_button.clicked.connect(self.accept)
        for botao in (self.pdf_button, self.print_button, self.close_button):
            botao.setFixedHeight(40)
            botao.setCursor(Qt.PointingHandCursor)
            botao.setStyleSheet(inventory.NEW_BUTTON_QSS)
            linha.addWidget(botao)
        return linha

    # --------------------------------------------------------------- saídas

    def sugerir_nome_do_arquivo(self) -> str:
        """Identificador curto no nome do arquivo.

        O uuid inteiro não cabe na coluna de nome de nenhum gerenciador, e o
        prefixo é justamente como a tela já identifica a venda.
        """
        return f"comprovante-{str(self.receipt.sale_id)[:8]}.pdf"

    def export_pdf(self, path: str) -> None:
        """Grava o PDF. Levanta `OSError` quando o destino recusa escrita.

        O destino é aberto AQUI, e não passado como caminho para o
        `QPdfWriter`: construído com um caminho, ele não levanta nada em
        pasta inexistente ou sem permissão — apenas falha o
        `QPainter::begin` por dentro e volta em silêncio. O diálogo então
        anunciava "comprovante salvo" sobre um arquivo que não existe.
        """
        destino = QFile(path)
        if not destino.open(QIODevice.WriteOnly):
            raise OSError(
                destino.errorString() or f"não foi possível escrever em {path}"
            )
        try:
            writer = QPdfWriter(destino)
            writer.setPageSize(QPageSize(QPageSize.A4))
            writer.setPageMargins(
                QMarginsF(MARGEM_MM, MARGEM_MM, MARGEM_MM, MARGEM_MM),
                QPageLayout.Millimeter,
            )
            documento = QTextDocument()
            documento.setHtml(self.html)
            documento.print_(writer)
        finally:
            destino.close()

    def _gravar_pdf(self, path: str) -> None:
        try:
            self.export_pdf(path)
        except Exception as erro:
            self._avisar(f"Não foi possível salvar o PDF: {erro}", erro=True)
            return
        self._avisar(f"Comprovante salvo em {path}.")

    def _escolher_destino(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar comprovante", self.sugerir_nome_do_arquivo(),
            "PDF (*.pdf)",
        )
        if path:
            self._gravar_pdf(path)

    def _imprimir(self):
        # `QtPrintSupport` é a única parte do Qt usada aqui que o resto do
        # aplicativo nunca carrega; importá-la na montagem do módulo faria
        # toda a suíte pagar por um recurso que só quem imprime usa.
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter

        try:
            printer = QPrinter(QPrinter.HighResolution)
            dialogo = QPrintDialog(printer, self)
            if dialogo.exec() != QDialog.Accepted:
                return
            documento = QTextDocument()
            documento.setHtml(self.html)
            documento.print_(printer)
        except Exception as erro:
            self._avisar(f"Não foi possível imprimir: {erro}", erro=True)
            return
        self._avisar("Comprovante enviado para a impressora.")

    def _avisar(self, mensagem, erro=False):
        self.status_label.setStyleSheet(
            inventory.LOAD_ERROR_QSS if erro
            else "color: #15803D; font-size: 13px;"
        )
        self.status_label.setText(mensagem)
        self.status_label.setVisible(True)
