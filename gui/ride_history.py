# gui/ride_history.py

from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
)
from PyQt5.QtCore import Qt


WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def seconds_to_hhmm(seconds) -> str:
    try:
        s = int(seconds)
    except Exception:
        return str(seconds)
    s = max(0, min(86399, s))
    h = s // 3600
    m = (s % 3600) // 60
    return f"{h:02d}:{m:02d}"


class RideHistoryPage(QWidget):
    """
    Shows ride history for the current user (driver or passenger).

    Expects MainWindow to provide:
        - current_username
        - current_role ("driver" or "passenger")
        - api_client (RealtimeClient or compatible)
    """

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        self.title_label = QLabel("Ride History")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self.title_label)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        controls = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_history)
        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self._on_back)
        controls.addWidget(self.refresh_btn)
        controls.addStretch()
        controls.addWidget(self.back_btn)
        layout.addLayout(controls)

        # Columns: one row per ride
        self.table = QTableWidget()
        self.table.setColumnCount(8)
        self.table.setHorizontalHeaderLabels(
            [
                "Ride ID",
                "Passenger",
                "Driver",
                "Area",
                "Weekday",
                "Time",
                "My Rating",
                "Their Rating",
            ]
        )
        self.table.setSelectionBehavior(self.table.SelectRows)
        self.table.setSelectionMode(self.table.SingleSelection)
        self.table.setEditTriggers(self.table.NoEditTriggers)
        layout.addWidget(self.table)

        layout.addStretch()

    # public: called from MainWindow when switching to page
    def refresh_ui(self):
        uname = self.main_window.current_username or "?"
        role = self.main_window.current_role or "?"
        self.info_label.setText(f"User: {uname} (role: {role})")
        self.refresh_history()

    def _on_back(self):
        role = self.main_window.current_role
        if role == "driver":
            self.main_window.show_driver_home()
        else:
            self.main_window.show_passenger_home()

    def refresh_history(self):
        client = self.main_window.api_client
        username = self.main_window.current_username
        role = self.main_window.current_role

        if not username or not role:
            QMessageBox.warning(self, "Not logged in", "Please log in again.")
            return

        try:
            resp = client.get_ride_history(username=username, role=role)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to contact server:\n{e}")
            return

        if resp.get("status") != "success":
            msg = resp.get("message", "Unknown error.")
            QMessageBox.critical(self, "Error", msg)
            return

        rides = resp.get("rides", []) or []
        self.table.setRowCount(len(rides))

        for row_idx, r in enumerate(rides):
            ride_id = r.get("id")
            passenger = r.get("passenger_username") or ""
            driver = r.get("driver_username") or ""
            area = r.get("area") or ""
            weekday_int = r.get("weekday")
            time_val = r.get("time")

            # Optional rating fields (per-ride)
            my_rating = (
                r.get("my_rating")
                or r.get("rating_given_by_me")
                or ""
            )
            their_rating = (
                r.get("their_rating")
                or r.get("rating_given_to_me")
                or ""
            )

            if isinstance(weekday_int, int) and 0 <= weekday_int < 7:
                weekday_str = WEEKDAY_NAMES[weekday_int]
            else:
                weekday_str = str(weekday_int)

            time_str = seconds_to_hhmm(time_val)

            self.table.setItem(row_idx, 0, QTableWidgetItem(str(ride_id)))
            self.table.setItem(row_idx, 1, QTableWidgetItem(passenger))
            self.table.setItem(row_idx, 2, QTableWidgetItem(driver))
            self.table.setItem(row_idx, 3, QTableWidgetItem(area))
            self.table.setItem(row_idx, 4, QTableWidgetItem(weekday_str))
            self.table.setItem(row_idx, 5, QTableWidgetItem(time_str))
            self.table.setItem(
                row_idx, 6, QTableWidgetItem(str(my_rating) if my_rating else "")
            )
            self.table.setItem(
                row_idx, 7, QTableWidgetItem(str(their_rating) if their_rating else "")
            )

        self.table.resizeColumnsToContents()
