#PREMIUM: CHOOSE THEME
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QRadioButton,
    QPushButton,
    QHBoxLayout,
)
from PyQt5.QtCore import Qt


class ThemeSettingsPage(QWidget):
    """
    Light or Dark mode
    MainWindow.apply_theme(theme_name) under the hood and
    reads the current theme from MainWindow.current_preferences.
    """

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        title = QLabel("Appearance & Theme")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 20px; font-weight: bold; margin-bottom: 8px;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Choose a basic theme for the AUBus application.\n"
            "Your choice will be saved with your account."
        )
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addSpacing(10)

        # Radio buttons for theme selection
        self.light_radio = QRadioButton("Light (default)")
        self.dark_radio = QRadioButton("Dark")

        layout.addWidget(self.light_radio)
        layout.addWidget(self.dark_radio)

        layout.addSpacing(10)

        #Info label
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setStyleSheet("color: gray;")
        layout.addWidget(self.info_label)

        layout.addStretch()

        #Buttons row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.apply_btn = QPushButton("Apply")
        self.apply_btn.clicked.connect(self._on_apply_clicked)

        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self._on_back_clicked)

        btn_row.addWidget(self.apply_btn)
        btn_row.addWidget(self.back_btn)

        layout.addLayout(btn_row)

    # public API
    def refresh_ui(self):
        """
        Called from MainWindow.show_theme_settings() before showing the page.
        """
        prefs = self.main_window.current_preferences or {}
        theme = prefs.get("theme") or prefs.get("theme_name") or "default"

        if theme == "dark":
            self.dark_radio.setChecked(True)
            self.light_radio.setChecked(False)
        else:
            # treat anything else as light/default
            self.light_radio.setChecked(True)
            self.dark_radio.setChecked(False)

        self.info_label.setText("")

    # internal handlers
    def _on_apply_clicked(self):
        if self.dark_radio.isChecked():
            theme_name = "dark"
        else:
            theme_name = "light"  # "light" / "default" share same style

        # Ask MainWindow to apply + save theme
        self.main_window.apply_theme(theme_name, save_to_server=True)

        self.info_label.setText(f"Theme '{theme_name}' applied and saved.")

    def _on_back_clicked(self):
        """
        Go back to the appropriate home page based on current role.
        """
        role = self.main_window.current_role
        if role == "driver":
            self.main_window.show_driver_home()
        elif role == "passenger":
            self.main_window.show_passenger_home()
        else:
            # If somehow not logged in, go to login
            self.main_window.show_login()
