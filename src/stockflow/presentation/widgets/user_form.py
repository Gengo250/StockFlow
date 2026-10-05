from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout,
)

from stockflow.presentation.demo_users import USER_ROLES


class UserForm(QDialog):
    def __init__(self, user=None, parent=None, pode_gerenciar=False, on_save=None):
        """Formulário de usuário.

        `pode_gerenciar` nasce `False` de propósito. O diálogo é construído
        direto por `tests/test_ui_regression.py` e pode vir a ser construído
        por outro caminho; abrir liberado e esperar que alguém trave é como
        um controle fica aberto quando esse alguém não é chamado.
        """
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
        from stockflow.presentation.roles import ROLE_LABELS
        for role, label in ROLE_LABELS.items():
            self.role_input.addItem(label, role.value)
        self.department_input = QLineEdit(user[2] if user and user[2] != "—" else "")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Senha inicial (somente para nova conta)")
        self.password_input.setVisible(not bool(user))
        self.login_input.setReadOnly(bool(user))
        for label, field in (("Nome", self.name_input), ("E-mail", self.login_input), ("Perfil", self.role_input)):
            fields.addRow(label, field)
        fields.addRow("Departamento", self.department_input)
        if not user:
            fields.addRow("Senha inicial", self.password_input)
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
        self.save_button = save
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)
        save.setEnabled(pode_gerenciar)
        self._on_save = on_save
        self._user = user
        save.clicked.connect(self._save)
        actions.addWidget(cancel)
        actions.addWidget(save)
        layout.addLayout(actions)

    def _save(self):
        if not self.save_button.isEnabled():
            return
        if self._on_save is None:
            self.error_label.setText("Abra este cadastro pela Administração de Usuários.")
            return
        try:
            self._on_save(user_id=getattr(self._user, "user_id", None),
                          name=self.name_input.text(), email=self.login_input.text(),
                          role=self.role_input.currentData(), department=self.department_input.text(),
                          password=self.password_input.text())
        except Exception as error:
            self.error_label.setText(str(error))
            return
        self.password_input.clear()
        self.accept()
