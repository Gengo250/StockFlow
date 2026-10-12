from datetime import date, datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout


def movement_datetime(value):
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, date):
        result = datetime.combine(value, datetime.min.time())
    else:
        try:
            result = datetime.fromisoformat(str(value))
        except ValueError:
            for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
                try:
                    return datetime.strptime(str(value), fmt)
                except ValueError:
                    continue
            return None
    if result.tzinfo is not None:
        result = result.astimezone(timezone.utc).replace(tzinfo=None)
    return result


class MovementDetailsDialog(QDialog):
    def __init__(self, movement, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle("Detalhes da movimentação")
        self.resize(540, 560)
        self.setStyleSheet("QDialog { background: #F0F5FF; } QLabel { color: #334155; font-size: 14px; }")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)
        title = QLabel("Histórico da movimentação")
        title.setStyleSheet("font-size: 22px; font-weight: 600; color: #0F172A;")
        layout.addWidget(title)
        form = QFormLayout()
        form.setSpacing(12)
        self.values = {}
        labels = (
            ("Identificador", movement[0]),
            ("Produto", f"{movement[1]} — {movement[2]}"),
            ("Tipo", movement[3]), ("Quantidade", movement[4]),
            ("Situação", movement[5]), ("Data", movement[7]),
            ("Saldo anterior", movement[9]), ("Saldo resultante", movement[10]),
            ("Origem", movement[11]), ("Responsável", movement[12]),
            ("Venda vinculada", movement[13]), ("Fornecedor / Cliente", movement[8]),
            ("Observação", movement[6]),
        )
        for name, value in labels:
            text = str(value) if value is not None and value != "" else "Não informado"
            field = QLabel(text)
            field.setWordWrap(True)
            field.setTextFormat(Qt.PlainText)
            field.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
            self.values[name] = field
            form.addRow(name, field)
        layout.addLayout(form)
        notice = QLabel("Consulta somente leitura. Movimentações confirmadas não podem ser editadas, excluídas ou canceladas diretamente.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox()
        buttons.addButton("Fechar", QDialogButtonBox.RejectRole)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
