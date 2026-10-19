import qtawesome as qta
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QListWidget, QListWidgetItem, QMessageBox, QFrame
)
from stockflow.presentation.styles.products import PRODUCTS_QSS


class CategoryDialog(QDialog):
    """Diálogo para gerir e criar novas categorias de produtos."""
    category_created = Signal(str)

    def __init__(self, categories, on_create_callback=None, parent=None):
        super().__init__(parent)
        self.setObjectName("categoryDialog")
        self.setWindowTitle("Gerenciar Categorias")
        self.setMinimumWidth(400)
        self.setMinimumHeight(450)
        self.setStyleSheet(PRODUCTS_QSS)

        self.categories = list(categories or [])
        self.on_create_callback = on_create_callback

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # Cabeçalho
        title = QLabel("Categorias de Produtos")
        title.setObjectName("pageTitle")
        layout.addWidget(title)

        subtitle = QLabel("Adicione ou consulte as categorias disponíveis no catálogo.")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        # Campo de Adição de Nova Categoria
        add_layout = QHBoxLayout()
        add_layout.setSpacing(10)
        
        self.input_new = QLineEdit()
        self.input_new.setPlaceholderText("Nome da nova categoria...")
        self.input_new.setFixedHeight(42)
        add_layout.addWidget(self.input_new, 1)

        self.btn_add = QPushButton("Adicionar")
        self.btn_add.setObjectName("newProductButton")
        self.btn_add.setFixedHeight(42)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._handle_create)
        add_layout.addWidget(self.btn_add)
        
        layout.addLayout(add_layout)

        # Lista de Categorias Existentes
        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet("""
            QListWidget {
                background: white;
                border: 1px solid #DBEAFE;
                border-radius: 12px;
                padding: 8px;
                font-size: 14px;
                color: #0F172A;
            }
            QListWidget::item {
                padding: 10px 12px;
                border-bottom: 1px solid #F1F5F9;
                border-radius: 6px;
            }
            QListWidget::item:hover {
                background: #F8FAFC;
            }
        """)
        layout.addWidget(self.list_widget, 1)

        # Botão Fechar
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()
        
        btn_close = QPushButton("Concluído")
        btn_close.setFixedHeight(38)
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.clicked.connect(self.accept)
        footer_layout.addWidget(btn_close)
        
        layout.addLayout(footer_layout)

        self._populate_list()

    def _populate_list(self):
        self.list_widget.clear()
        for cat in sorted(self.categories):
            item = QListWidgetItem(cat)
            self.list_widget.addItem(item)

    def _handle_create(self):
        name = self.input_new.text().strip()
        if not name:
            QMessageBox.warning(self, "Nome Inválido", "O nome da categoria não pode estar vazio.")
            return
        
        if name in self.categories:
            QMessageBox.warning(self, "Categoria Duplicada", "Esta categoria já existe.")
            return

        if self.on_create_callback is not None:
            try:
                self.on_create_callback(name)
            except Exception as e:
                QMessageBox.warning(self, "Erro ao criar", str(e))
                return

        self.categories.append(name)
        self._populate_list()
        self.input_new.clear()
        self.category_created.emit(name)