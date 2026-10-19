from pathlib import Path

import qtawesome as qta
from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QSpinBox, QVBoxLayout, QWidget,
)


LABEL_QSS = "background-color: transparent;"
FIELD_QSS = """
    {widget} {{
        background-color: #FFFFFF;
        color: #0F172A;
        border: 1px solid #CBD5E1;
        border-radius: 10px;
        padding: 0px 12px;
        font-size: 14px;
    }}
    {widget}:focus {{ border: 2px solid #93C5FD; }}
"""


FORM_CONTROL_QSS = "\n".join(
    FIELD_QSS.format(widget=kind)
    for kind in ("QLineEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox", "QDateEdit")
) + """
    QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 24px; }
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
        width: 20px; border: none; background: transparent;
    }
    QComboBox:disabled, QDateEdit:disabled, QSpinBox:disabled,
    QLineEdit:disabled { color: #94A3B8; background: #F8FAFC; }
"""


_ASSETS = Path(__file__).resolve().parents[1] / "assets"
FORM_CONTROL_QSS += """
    QComboBox::down-arrow, QDateEdit::down-arrow,
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        image: url("DOWN_ICON"); width: 10px; height: 10px;
    }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        image: url("UP_ICON"); width: 10px; height: 10px;
    }
""".replace("DOWN_ICON", (_ASSETS / "chevron-down.svg").as_posix()).replace(
    "UP_ICON", (_ASSETS / "chevron-up.svg").as_posix()
)


def _card(object_name):
    card = QFrame()
    card.setObjectName(object_name)
    card.setStyleSheet(f"""
        QFrame#{object_name} {{
            background-color: #FFFFFF;
            border: 1px solid #DBEAFE;
            border-radius: 16px;
        }}
        QFrame#{object_name} QLabel {{ background-color: transparent; }}
    """)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(22, 22, 22, 22)
    layout.setSpacing(16)
    return card


def _divider():
    divider = QFrame()
    divider.setFixedHeight(1)
    divider.setStyleSheet("background-color: #EFF6FF; border: none;")
    return divider


def _card_header(icon_name, title_text, subtitle_text):
    layout = QHBoxLayout()
    layout.setSpacing(12)

    icon_container = QFrame()
    icon_container.setFixedSize(38, 38)
    icon_container.setStyleSheet(
        "background-color: #EFF6FF; border: none; border-radius: 10px;"
    )
    icon_layout = QVBoxLayout(icon_container)
    icon_layout.setContentsMargins(0, 0, 0, 0)
    icon = QLabel()
    icon.setAlignment(Qt.AlignCenter)
    icon.setPixmap(qta.icon(icon_name, color="#2563EB").pixmap(16, 16))
    icon_layout.addWidget(icon)

    text_container = QWidget()
    text_layout = QVBoxLayout(text_container)
    text_layout.setContentsMargins(0, 0, 0, 0)
    text_layout.setSpacing(2)
    title = QLabel(title_text)
    title.setStyleSheet(
        f"{LABEL_QSS} color: #0F172A; font-size: 16px; font-weight: 600;"
    )
    title.setWordWrap(True)
    subtitle = QLabel(subtitle_text)
    subtitle.setWordWrap(True)
    subtitle.setStyleSheet(f"{LABEL_QSS} color: #94A3B8; font-size: 12px;")
    text_layout.addWidget(title)
    text_layout.addWidget(subtitle)

    layout.addWidget(icon_container)
    layout.addWidget(text_container, 1)
    return layout


def _field(label_text, optional=False):
    container = QWidget()
    layout = QVBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)

    label_row = QHBoxLayout()
    label = QLabel(label_text)
    label.setStyleSheet(
        f"{LABEL_QSS} color: #475569; font-size: 13px; font-weight: 500;"
    )
    label_row.addWidget(label)
    if optional:
        optional_label = QLabel("(opcional)")
        optional_label.setStyleSheet(
            f"{LABEL_QSS} color: #94A3B8; font-size: 12px;"
        )
        label_row.addWidget(optional_label)
    label_row.addStretch()
    layout.addLayout(label_row)
    return container


def _line_edit(placeholder=""):
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    widget.setFixedHeight(42)
    widget.setStyleSheet(FIELD_QSS.format(widget="QLineEdit"))
    return widget


def _combo(items):
    widget = QComboBox()
    widget.addItems(items)
    widget.setFixedHeight(42)
    widget.setStyleSheet(
        FIELD_QSS.format(widget="QComboBox")
        + "QComboBox::drop-down { border: none; width: 30px; }"
    )
    return widget


def _money_input():
    widget = QDoubleSpinBox()
    widget.setLocale(QLocale("pt_BR"))
    widget.setGroupSeparatorShown(True)
    widget.setRange(0, 99999999.99)
    widget.setDecimals(2)
    widget.setSingleStep(1)
    widget.setPrefix("R$ ")
    widget.setFixedHeight(42)
    widget.setStyleSheet(
        FIELD_QSS.format(widget="QDoubleSpinBox")
        + "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button "
          "{ width: 20px; border: none; background-color: transparent; }"
    )
    return widget


def _stock_input():
    widget = QSpinBox()
    widget.setRange(0, 999999)
    widget.setSingleStep(1)
    widget.setFixedHeight(42)
    widget.setStyleSheet(
        FIELD_QSS.format(widget="QSpinBox")
        + "QSpinBox::up-button, QSpinBox::down-button "
          "{ width: 20px; border: none; background-color: transparent; }"
    )
    return widget


# Valor interno que representa "sem mínimo" no QSpinBox. Um spin sempre tem
# um número; `setSpecialValueText` troca a exibição do EXTREMO do range por um
# texto. Por isso o range começa em -1: ele é o extremo, nunca um mínimo
# válido (a coluna tem CHECK >= 0), e descer de 0 pelas setas chega nele.
SEM_MINIMO = -1


def _minimum_stock_input():
    """Spin de estoque mínimo, capaz de representar AUSÊNCIA.

    Separado de `_stock_input` de propósito: o estoque inicial não tem
    conceito de "ausente" e -1 ali seria um valor sem sentido esperando para
    virar bug.
    """
    widget = _stock_input()
    widget.setRange(SEM_MINIMO, 999999)
    widget.setSpecialValueText("Sem mínimo")
    widget.setToolTip(
        "Deixe em \"Sem mínimo\" para não receber alerta deste produto. "
        "Zero significa avisar quando o estoque acabar."
    )
    return widget


def _maximum_stock_input():
    """Spin de estoque máximo, inteiro não-negativo.

    Assim como o mínimo, o máximo pode estar "sem configurar" (None).
    O valor exibido é sempre um número ≥ 0; "Sem máximo" indica que
    não há limite definido.
    """
    widget = _stock_input()
    widget.setRange(0, 999999)
    widget.setSpecialValueText("Sem máximo")
    widget.setToolTip(
        "Defina o estoque máximo para este produto. "
        "O sistema bloqueará definições abaixo do estoque mínimo configurado."
    )
    return widget


class FormCard(QFrame):
    def __init__(self, object_name):
        super().__init__()
        card = _card(object_name)
        self.content_layout = card.layout()
        wrapper = QVBoxLayout(self)
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.addWidget(card)
