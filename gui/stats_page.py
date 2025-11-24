#PREMIUM FEATURES: PERSONAL STATSS
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

class StatsPage(QWidget):
    """
    Premium 'My Stats' info.
    Shows, depending on role:
      - Total rides
      - Distinct drivers or passengers
      - Rides per weekday
      - Average rating received
    """
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        self.title_label = QLabel("My Stats")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")
        layout.addWidget(self.title_label)

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)

        #Summary labels
        self.summary_label = QLabel("")
        self.summary_label.setAlignment(Qt.AlignCenter)
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        #Weekday stats table
        weekday_box = QVBoxLayout()
        weekday_title = QLabel("Rides per weekday")
        weekday_title.setAlignment(Qt.AlignLeft)
        weekday_title.setStyleSheet("font-weight: bold;")
        weekday_box.addWidget(weekday_title)

        self.weekday_table = QTableWidget()
        self.weekday_table.setColumnCount(2)
        self.weekday_table.setHorizontalHeaderLabels(["Weekday", "Rides"])
        self.weekday_table.setSelectionMode(self.weekday_table.NoSelection)
        self.weekday_table.setEditTriggers(self.weekday_table.NoEditTriggers)
        weekday_box.addWidget(self.weekday_table)

        layout.addLayout(weekday_box)

        layout.addStretch()

        # Buttons row
        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_ui)

        self.back_btn = QPushButton("Back")
        self.back_btn.clicked.connect(self._on_back)

        btn_row.addWidget(self.refresh_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.back_btn)

        layout.addLayout(btn_row)

    # public API
    def refresh_ui(self):
        """
        Called by MainWindow.show_stats_page() and fetches data from server and updates the stats.
        """
        username = self.main_window.current_username
        role = self.main_window.current_role

        if not username or not role:
            QMessageBox.warning(self, "Not logged in", "Please log in again.")
            self.info_label.setText("Not logged in.")
            self.summary_label.setText("")
            self._clear_weekday_table()
            return

        self.info_label.setText(f"User: {username} (role: {role})")

        client = self.main_window.api_client

        #Fetch ride history for this user
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

        #Compute stats from history
        total_rides = len(rides)

        # Distinct counterparties, rides per weekday
        distinct_drivers = set()
        distinct_passengers = set()
        weekday_counts = {i: 0 for i in range(7)}

        for r in rides:
            weekday_int = r.get("weekday")
            if isinstance(weekday_int, int) and 0 <= weekday_int < 7:
                weekday_counts[weekday_int] += 1

            passenger = r.get("passenger_username") or ""
            driver = r.get("driver_username") or ""

            if passenger:
                distinct_passengers.add(passenger)
            if driver:
                distinct_drivers.add(driver)

        #Fetch average rating from the server
        avg_rating = None
        try:
            r_resp = client.get_rating(username)
            if r_resp.get("status") == "success":
                avg_rating = r_resp.get("rating")
        except Exception:
            avg_rating = None

        if avg_rating is None:
            rating_text = "No ratings yet"
        else:
            rating_text = f"{avg_rating:.2f} / 5"

        #Build summary text depending on role
        summary_parts = []

        if role == "passenger":
            # Passenger-only stats
            summary_parts.append(f"Total rides (as passenger): {total_rides}")
            summary_parts.append(
                f"Distinct drivers you rode with: {len(distinct_drivers)}"
            )
        elif role == "driver":
            # Driver-only stats
            summary_parts.append(f"Total rides (as driver): {total_rides}")
            summary_parts.append(
                f"Distinct passengers you carried: {len(distinct_passengers)}"
            )
        else:
            # Fallback, if role somehow unknown
            summary_parts.append(f"Total rides: {total_rides}")
            summary_parts.append(f"Distinct passengers: {len(distinct_passengers)}")
            summary_parts.append(f"Distinct drivers: {len(distinct_drivers)}")

        summary_parts.append(f"Average rating received: {rating_text}")

        self.summary_label.setText("\n".join(summary_parts))

        #Fill weekday table
        self._fill_weekday_table(weekday_counts)

    #internal helpers
    def _clear_weekday_table(self):
        self.weekday_table.setRowCount(0)

    def _fill_weekday_table(self, weekday_counts: dict):
        self.weekday_table.setRowCount(7)
        for i in range(7):
            day_name = WEEKDAY_NAMES[i]
            count = weekday_counts.get(i, 0)
            self.weekday_table.setItem(i, 0, QTableWidgetItem(day_name))
            self.weekday_table.setItem(i, 1, QTableWidgetItem(str(count)))
        self.weekday_table.resizeColumnsToContents()

    def _on_back(self):
        role = self.main_window.current_role
        if role == "driver":
            self.main_window.show_driver_home()
        elif role == "passenger":
            self.main_window.show_passenger_home()
        else:
            self.main_window.show_login()
