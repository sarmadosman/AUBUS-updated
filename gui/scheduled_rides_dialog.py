from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
)
from PyQt5.QtCore import Qt


def _seconds_to_hhmm(sec):
    try:
        sec = int(sec)
    except Exception:
        return str(sec)
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h:02d}:{m:02d}"


class ScheduledRidesDialog(QDialog):
    """
    Shared "My scheduled rides" dialog for both passengers and drivers.
    """

    def __init__(self, main_window, role: str, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.role = role

        self.setWindowTitle("My scheduled rides")
        self.setModal(True)
        self.resize(700, 400)

        self._build_ui()
        self._load_rides()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("My scheduled rides")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(title)

        role_label = QLabel(f"Role: {self.role}")
        role_label.setAlignment(Qt.AlignCenter)
        role_label.setStyleSheet("color: gray;")
        layout.addWidget(role_label)

        self.table = QTableWidget()
        self.table.setSelectionBehavior(self.table.SelectRows)
        self.table.setSelectionMode(self.table.SingleSelection)
        self.table.setEditTriggers(self.table.NoEditTriggers)

        if self.role == "driver":
            headers = ["ID", "Passenger", "Area", "Date", "Time", "Status"]
        else:
            headers = ["ID", "Driver", "Area", "Date", "Time", "Status"]

        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        layout.addWidget(self.table)

        # Buttons row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._load_rides)
        btn_row.addWidget(self.refresh_btn)

        if self.role == "driver":
            self.accept_btn = QPushButton("Accept selected")
            self.accept_btn.clicked.connect(self._on_accept_selected)
            self.decline_btn = QPushButton("Decline selected")
            self.decline_btn.clicked.connect(self._on_decline_selected)

            btn_row.addWidget(self.accept_btn)
            btn_row.addWidget(self.decline_btn)
        else:
            self.cancel_btn = QPushButton("Cancel selected")
            self.cancel_btn.clicked.connect(self._on_cancel_selected)
            btn_row.addWidget(self.cancel_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)

        layout.addLayout(btn_row)

    #Data loading
    def _load_rides(self):
        username = self.main_window.current_username or ""
        client = self.main_window.api_client

        try:
            resp = client.get_scheduled_rides(username=username, role=self.role)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load scheduled rides from server:\n{e}",
            )
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self,
                "Error",
                resp.get("message", "Failed to load scheduled rides."),
            )
            return

        rides = resp.get("rides", []) or []
        self._populate_table(rides)

    def _populate_table(self, rides):
        self.table.setRowCount(len(rides))
        for row, r in enumerate(rides):
            ride_id = r.get("id")
            passenger = r.get("passenger_username", "")
            driver = r.get("driver_username", "")
            area = r.get("area", "")
            date = r.get("date", "")
            time_val = r.get("time", "")
            status = r.get("status", "")

            if isinstance(time_val, int):
                time_str = _seconds_to_hhmm(time_val)
            else:
                time_str = str(time_val)

            if self.role == "driver":
                other = passenger
            else:
                other = driver

            self.table.setItem(row, 0, QTableWidgetItem(str(ride_id)))
            self.table.setItem(row, 1, QTableWidgetItem(str(other)))
            self.table.setItem(row, 2, QTableWidgetItem(str(area)))
            self.table.setItem(row, 3, QTableWidgetItem(str(date)))
            self.table.setItem(row, 4, QTableWidgetItem(str(time_str)))
            self.table.setItem(row, 5, QTableWidgetItem(str(status)))

    def _get_selected_ride_id(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No selection", "Please select a ride first.")
            return None

        id_item = self.table.item(row, 0)
        if id_item is None:
            QMessageBox.warning(self, "Error", "Selected row is missing ID.")
            return None

        try:
            ride_id = int(id_item.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid ride ID.")
            return None

        return ride_id

    # Driver actions
    def _on_accept_selected(self):
        if self.role != "driver":
            return
        ride_id = self._get_selected_ride_id()
        if ride_id is None:
            return

        client = self.main_window.api_client
        try:
            resp = client.driver_accept_scheduled_ride(ride_id)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to accept scheduled ride:\n{e}",
            )
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self,
                "Error",
                resp.get("message", "Could not accept scheduled ride."),
            )
            return

        QMessageBox.information(self, "Scheduled ride", "Scheduled ride accepted.")
        self._load_rides()

    def _on_decline_selected(self):
        if self.role != "driver":
            return
        ride_id = self._get_selected_ride_id()
        if ride_id is None:
            return

        client = self.main_window.api_client
        try:
            resp = client.driver_decline_scheduled_ride(ride_id)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to decline scheduled ride:\n{e}",
            )
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self,
                "Error",
                resp.get("message", "Could not decline scheduled ride."),
            )
            return

        QMessageBox.information(self, "Scheduled ride", "Scheduled ride declined.")
        self._load_rides()

    # Passenger actions
    def _on_cancel_selected(self):
        if self.role != "passenger":
            return
        ride_id = self._get_selected_ride_id()
        if ride_id is None:
            return

        res = QMessageBox.question(
            self,
            "Cancel scheduled ride",
            "Are you sure you want to cancel this scheduled ride?",
        )
        if res != QMessageBox.Yes:
            return

        client = self.main_window.api_client
        try:
            resp = client.passenger_cancel_scheduled_ride(ride_id)
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to cancel scheduled ride:\n{e}",
            )
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self,
                "Error",
                resp.get("message", "Could not cancel scheduled ride."),
            )
            return

        QMessageBox.information(self, "Scheduled ride", "Scheduled ride cancelled.")
        self._load_rides()
