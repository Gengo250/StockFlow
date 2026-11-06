"""Read-only presentation of the fields supplied by the price audit contract."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFrame, QGridLayout, QLabel, QPushButton, QVBoxLayout

from stockflow.domain.permissions import exigir_ver
from stockflow.infrastructure.repositories.product_mapper import money_to_label
from stockflow.presentation.styles import design_system as ds
from stockflow.presentation.styles import inventory


class AuditEventDialog(QDialog):
    def __init__(self, change, session, parent=None):
        exigir_ver(session, 'historico_precos', 'consultar detalhes do evento')
        super().__init__(parent)
        self.setWindowTitle('Detalhes do evento')
        self.setObjectName('auditEventDialog')
        self.setMinimumWidth(540)
        self.resize(680, 480)
        self.setStyleSheet(ds.page_qss('auditEventDialog') +
                          ds.surface_qss('QFrame#auditMetadata, QFrame#auditComparison'))
        layout = QVBoxLayout(self)
        ds.page_layout(layout)

        def label(text, style=None):
            widget = QLabel(text)
            widget.setTextFormat(Qt.PlainText)
            widget.setWordWrap(True)
            widget.setTextInteractionFlags(Qt.TextSelectableByMouse)
            if style:
                widget.setStyleSheet(style)
            return widget

        layout.addWidget(label('Detalhes do evento', ds.TITLE_QSS))
        layout.addWidget(label('Auditoria de preços e custos · Somente leitura', ds.SUBTITLE_QSS))
        metadata = QFrame()
        metadata.setObjectName('auditMetadata')
        grid = QGridLayout(metadata)
        grid.setContentsMargins(20, 18, 20, 18)
        grid.setVerticalSpacing(14)
        when = (change.changed_on.astimezone().strftime('%d/%m/%Y %H:%M:%S %Z')
                if change.changed_on else 'Não informado')
        product = f'{change.product_code} — {change.product_name}'.strip(' —')
        for row, (name, value) in enumerate((
            ('Quando', when), ('Usuário', change.changed_by or 'Não informado'),
            ('Ação', 'Alteração de preço de venda' if change.field.value == 'SELL_PRICE'
             else 'Alteração de custo'),
            ('Entidade', 'Produto'), ('Produto', product or 'Produto não disponível'),
        )):
            grid.addWidget(label(name, ds.SUBTITLE_QSS), row, 0)
            grid.addWidget(label(value), row, 1)
        grid.setColumnStretch(1, 1)
        layout.addWidget(metadata)
        layout.addWidget(label('Valores do evento', ds.SECTION_TITLE_QSS))
        comparison = QFrame()
        comparison.setObjectName('auditComparison')
        values = QGridLayout(comparison)
        values.setContentsMargins(20, 18, 20, 18)
        for col, (title, value) in enumerate((('Valor anterior', change.old_price),
                                             ('Valor novo', change.new_price))):
            values.addWidget(label(title, ds.SUBTITLE_QSS), 0, col)
            values.addWidget(label('Não informado' if value is None else money_to_label(value),
                                   ds.METRIC_QSS), 1, col)
            values.setColumnStretch(col, 1)
        layout.addWidget(comparison)
        layout.addStretch()
        back = QPushButton('Voltar ao histórico')
        back.setFixedHeight(ds.CONTROL_HEIGHT)
        back.setStyleSheet(inventory.FILTER_QSS)
        back.clicked.connect(self.close)
        layout.addWidget(back, alignment=Qt.AlignRight)
