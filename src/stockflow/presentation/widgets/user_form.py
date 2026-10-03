from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)

from stockflow.presentation.demo_users import USER_ROLES


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
        self.login_input.setPlaceholderText("E-mail do usuário")
        self.role_input = QComboBox()
        self.role_input.addItems(USER_ROLES)
        for label, field in (("Nome", self.name_input), ("E-mail", self.login_input), ("Perfil", self.role_input)):
            fields.addRow(label, field)
        if user:
            # Linha de demo_data:
            # (nome, login, departamento, perfil, status, último acesso, cor).
            # user[2] é o departamento, não o perfil: lido como perfil, o combo
            # caía no primeiro item e a edição mostrava o cargo errado.
            self.name_input.setText(user[0])
            self.login_input.setText(user[1])
            self.role_input.setCurrentText(user[3])
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
