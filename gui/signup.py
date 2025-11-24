from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
    QGroupBox,
)
from PyQt5.QtCore import Qt

from client import api_client
class SignupPage(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignTop)

        title = QLabel("Create AUBus Account")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 22px; font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(title)


        # Basic info
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)

        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.area_edit = QLineEdit()

        self.role_combo = QComboBox()
        self.role_combo.addItems(["passenger", "driver"])
        self.role_combo.currentTextChanged.connect(self._on_role_changed)

        form.addRow("Username:", self.username_edit)
        form.addRow("Password:", self.password_edit)
        form.addRow("Name:", self.name_edit)
        form.addRow("Email:", self.email_edit)
        form.addRow("Area:", self.area_edit)
        form.addRow("Role:", self.role_combo)

        main_layout.addLayout(form)

        
        # Weekly schedule for drivers
        self.schedule_group = QGroupBox("Weekly departure schedule (drivers only)")
        sched_layout = QFormLayout(self.schedule_group)

        self.day_edits = {}
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        for d in days:
            e = QLineEdit()
            e.setPlaceholderText("HH:MM (e.g. 08:30) or leave blank")
            self.day_edits[d] = e
            sched_layout.addRow(f"{d}:", e)

        main_layout.addWidget(self.schedule_group)

        self._on_role_changed(self.role_combo.currentText())

        # Buttons
        btn_row = QHBoxLayout()

        self.signup_btn = QPushButton("Sign up")
        self.signup_btn.clicked.connect(self._on_signup_clicked)

        self.back_btn = QPushButton("Back to Login")
        self.back_btn.clicked.connect(self.main_window.show_login)

        btn_row.addWidget(self.signup_btn)
        btn_row.addWidget(self.back_btn)

        main_layout.addLayout(btn_row)
        main_layout.addStretch()

    
    # Show/hide schedule group
    def _on_role_changed(self, role: str):
        is_driver = (role == "driver")
        self.schedule_group.setVisible(is_driver)
    
    # Signup logic
    def _on_signup_clicked(self):
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        name = self.name_edit.text().strip() or username
        email = self.email_edit.text().strip() or f"{username}@example.com"
        area = self.area_edit.text().strip()
        role = self.role_combo.currentText()

        if not username or not password or not area:
            QMessageBox.warning(self, "Missing info", "Username, password, and area are required.")
            return

        weekly_schedule = None
        if role == "driver":
            schedule = {}
            for day, edit in self.day_edits.items():
                t = edit.text().strip()
                if t:
                    schedule[day] = t
            if schedule:
                weekly_schedule = schedule

        # Call backend via API client
        resp = api_client.register_user(
            username=username,
            password=password,
            area=area,
            role=role,
            name=name,
            email=email,
            weekly_schedule=weekly_schedule,
        )

        if resp.get("status") != "success":
            msg = resp.get("message", "Registration failed.")
            QMessageBox.critical(self, "Sign up failed", msg)
            return

        QMessageBox.information(self, "Sign up", "Account created successfully. You can now log in.")
        # Go back to login page
        self.main_window.show_login()
