from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFormLayout,
)
from PyQt5.QtCore import Qt

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class ProfileDialog(QDialog):
    """
    Dialog to edit profile information:
      - name
      - email
      - area
      - password (optional)
      - weekly schedule (drivers only)
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.role = main_window.current_role  # "driver" or "passenger"

        self.setWindowTitle("Edit Profile")
        self.setModal(True)

        self.schedule_edits = {}  # day -> QLineEdit

        self._build_ui()
        self._load_profile()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Edit your profile")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: gray;")
        layout.addWidget(self.info_label)

        # ----- Basic info form -----
        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.email_edit = QLineEdit()
        self.area_edit = QLineEdit()

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        self.password_edit.setPlaceholderText("Leave empty to keep current password")

        form.addRow("Name:", self.name_edit)
        form.addRow("Email:", self.email_edit)
        form.addRow("Area:", self.area_edit)
        form.addRow("New password:", self.password_edit)

        layout.addLayout(form)

        # ==============================
        # SHOW WEEKLY SCHEDULE *ONLY* FOR DRIVERS
        # ==============================
        if self.role == "driver":
            schedule_label = QLabel("Weekly schedule (HH:MM, optional)")
            schedule_label.setAlignment(Qt.AlignLeft)
            schedule_label.setStyleSheet("font-weight: bold; margin-top: 8px;")
            layout.addWidget(schedule_label)

            sched_form = QFormLayout()
            for day in DAYS:
                edit = QLineEdit()
                edit.setPlaceholderText("e.g. 08:30 or leave empty")
                self.schedule_edits[day] = edit
                sched_form.addRow(f"{day}:", edit)

            layout.addLayout(sched_form)

        # ----- Buttons -----
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        self.save_btn.clicked.connect(self._on_save)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

    def _load_profile(self):
        user = self.main_window.current_username or ""
        self.info_label.setText(f"User: {user} ({self.role})")

        client = self.main_window.api_client
        try:
            resp = client.get_profile()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load profile:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(self, "Error", resp.get("message", "Failed."))
            return

        # Basic fields
        self.name_edit.setText(resp.get("name", "") or "")
        self.email_edit.setText(resp.get("email", "") or "")
        self.area_edit.setText(resp.get("area", "") or "")
        self.password_edit.clear()

        # Load schedule ONLY if driver
        if self.role == "driver":
            schedule = resp.get("weekly_schedule") or {}
            for day in DAYS:
                val = schedule.get(day, "")
                self.schedule_edits[day].setText(val or "")

    def _on_save(self):
        name = self.name_edit.text().strip()
        email = self.email_edit.text().strip()
        area = self.area_edit.text().strip()
        new_password = self.password_edit.text().strip()

        if not name or not email or not area:
            QMessageBox.warning(self, "Missing data", "Name, email, and area are required.")
            return

        weekly_schedule = {}

        # Only drivers have schedule fields
        if self.role == "driver":
            for day in DAYS:
                val = self.schedule_edits[day].text().strip()
                if val:
                    weekly_schedule[day] = val

        client = self.main_window.api_client
        try:
            resp = client.update_profile(
                name=name,
                email=email,
                area=area,
                password=new_password if new_password else None,
                weekly_schedule=weekly_schedule if self.role == "driver" else None,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update profile:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(self, "Error", resp.get("message", "Failed."))
            return

        self.main_window.current_area = area

        QMessageBox.information(self, "Saved", "Profile updated successfully.")
        self.accept()
