from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)


class UserForm(QDialog):
    def __init__(self, user=None, parent=None):
        super().__init__(parent)
        self.setObjectName("userForm")
        self.setWindowTitle("Editar usuário" if user else "Novo usuário")
        self.setMinimumWidth(480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)
        title = QLabel(self.windowTitle())
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        subtitle = QLabel("Atualize as informações da conta." if user else "Preencha os dados da nova conta.")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)
        fields = QFormLayout()
        fields.setSpacing(14)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Nome completo")
        self.login_input = QLineEdit()
        self.login_input.setPlaceholderText("Login do usuário")
        self.role_input = QComboBox()
        self.role_input.addItems(["Operador", "Gerente", "Administrador", "Financeiro"])
        self.status_input = QComboBox()
        self.status_input.addItems(["Ativo", "Inativo", "Pendente"])
        for label, field in (("Nome", self.name_input), ("Login", self.login_input), ("Perfil", self.role_input), ("Status", self.status_input)):
            fields.addRow(label, field)
        self.password_input = None
        if user:
            self.name_input.setText(user[0])
            self.login_input.setText(user[1])
            self.role_input.setCurrentText(user[3])
            self.status_input.setCurrentText(user[4])
        else:
            self.password_input = QLineEdit()
            self.password_input.setEchoMode(QLineEdit.Password)
            self.password_input.setPlaceholderText("Digite uma senha")
            fields.addRow("Senha", self.password_input)
        layout.addLayout(fields)
        actions = QHBoxLayout()
        actions.addStretch()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Salvar alterações" if user else "Cadastrar usuário")
        save.setObjectName("primaryButton")
        save.setEnabled(False)
        save.setToolTip("Disponível após integração das operações administrativas")
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)
