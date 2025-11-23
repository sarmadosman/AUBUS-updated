# gui/login.py

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)
from PyQt5.QtCore import Qt


class LoginPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel("AUBus Login")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)

        self.user_edit = QLineEdit()
        self.user_edit.setPlaceholderText("Username")
        layout.addWidget(self.user_edit)

        self.pass_edit = QLineEdit()
        self.pass_edit.setPlaceholderText("Password")
        self.pass_edit.setEchoMode(QLineEdit.Password)
        layout.addWidget(self.pass_edit)

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self._on_login_clicked)
        layout.addWidget(self.login_btn)

        self.signup_btn = QPushButton("Sign up")
        self.signup_btn.clicked.connect(self.main_window.show_signup)
        layout.addWidget(self.signup_btn)

    def _on_login_clicked(self):
        username = self.user_edit.text().strip()
        password = self.pass_edit.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Missing info", "Please enter username and password.")
            return

        resp = self.main_window.attempt_login(username, password)

        if resp.get("status") != "success":
            msg = resp.get("message", "Login failed.")
            QMessageBox.critical(self, "Login failed", msg)
            return

        # If we get here, MainWindow already navigated to the correct home page.
        QMessageBox.information(self, "Login", "Login successful.")
