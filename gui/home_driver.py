from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QTextEdit,
    QLineEdit,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
import socket
import random
from datetime import datetime

from gui.rating_dialog import RatingDialog
from gui.weather import WeatherApp
from gui.profile_dialog import ProfileDialog   # Profile editor dialog
from gui.scheduled_rides_dialog import ScheduledRidesDialog  # NEW


def _now_hhmm() -> str:
    """Return current time as HH:MM for compact chat timestamps."""
    t = datetime.now().time()
    return f"{t.hour:02d}:{t.minute:02d}"


class DriverChatServer(QThread):
    received = pyqtSignal(str)
    typing = pyqtSignal()
    disconnected = pyqtSignal()

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self.port = port
        self.sock = None
        self.client_sock = None
        self._running = True

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.sock.bind(("0.0.0.0", self.port))
            self.sock.listen(1)

            self.client_sock, _ = self.sock.accept()

            while self._running:
                data = self.client_sock.recv(1024)
                if not data:
                    break
                text = data.decode("utf-8")
                if text.strip() == "__TYPING__":
                    # Passenger is typing
                    self.typing.emit()
                    continue
                self.received.emit(text)
        except Exception:
            pass
        finally:
            self._close()

    def send(self, msg: str):
        try:
            if self.client_sock:
                self.client_sock.send(msg.encode("utf-8"))
        except Exception:
            pass

    def send_typing(self):
        """Send a small control message to indicate typing to passenger."""
        try:
            if self.client_sock:
                self.client_sock.send(b"__TYPING__")
        except Exception:
            pass

    def disconnect(self):
        self._running = False
        self._close()

    def _close(self):
        try:
            if self.client_sock:
                self.client_sock.close()
        except Exception:
            pass
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.disconnected.emit()


class HomeDriver(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.chat_server: DriverChatServer | None = None
        self.current_ride_id = None
        self.passenger_username = None

        # Weather window
        self.weather_window: WeatherApp | None = None

        # Driver availability status
        self.current_status = "available"

        # Typing indicator timer
        self._typing_timer: QTimer | None = None

        # For rate-limiting typing notifications
        self._last_typing_sent_ts: float | None = None

        self._build_ui()

    def shutdown(self):
        """
        Stop the driver chat server thread cleanly.
        Called from MainWindow on logout.
        """
        if self.chat_server:
            try:
                self.chat_server.disconnect()
                # Wait up to 2 seconds for the QThread to finish
                self.chat_server.wait(2000)
            except Exception:
                pass
            self.chat_server = None

    #UI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        self.title_label = QLabel("Driver Home")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.info_label)

        #STATUS RWO
        status_row = QHBoxLayout()
        self.status_label = QLabel("Status: available")
        self.status_label.setAlignment(Qt.AlignLeft)

        self.status_available_btn = QPushButton("Available")
        self.status_available_btn.clicked.connect(self._set_status_available)

        self.status_dnd_btn = QPushButton("Do Not Disturb")
        self.status_dnd_btn.clicked.connect(self._set_status_dnd)

        status_row.addWidget(self.status_label)
        status_row.addStretch()
        status_row.addWidget(self.status_available_btn)
        status_row.addWidget(self.status_dnd_btn)
        layout.addLayout(status_row)

        #RIDE BUTTONS
        btn_row = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh rides")
        self.refresh_btn.clicked.connect(self._on_refresh)

        self.accept_btn = QPushButton("Accept selected")
        self.accept_btn.clicked.connect(self._on_accept_selected)

        self.decline_btn = QPushButton("Decline selected")
        self.decline_btn.clicked.connect(self._on_decline_selected)

        self.complete_btn = QPushButton("Complete ride")
        self.complete_btn.clicked.connect(self._on_complete_ride)
        self.complete_btn.setEnabled(False)

        btn_row.addWidget(self.refresh_btn)
        btn_row.addWidget(self.accept_btn)
        btn_row.addWidget(self.decline_btn)
        btn_row.addWidget(self.complete_btn)

        layout.addLayout(btn_row)

        #PENDING RIDES TABLE
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Passenger", "Area", "Time", "Weekday", "Passenger Rating"]
        )
        self.table.setSelectionBehavior(self.table.SelectRows)
        self.table.setSelectionMode(self.table.SingleSelection)
        self.table.setEditTriggers(self.table.NoEditTriggers)
        layout.addWidget(self.table)

        # Chat UI
        layout.addWidget(QLabel("Chat:"))
        self.chat_box = QTextEdit()
        self.chat_box.setReadOnly(True)

        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Type a message...")
        self.chat_input.textEdited.connect(self._on_chat_typing)

        self.chat_send = QPushButton("Send")
        self.chat_send.clicked.connect(self._send_chat)

        # Quick message buttons
        quick_row = QHBoxLayout()
        self.quick_on_way_btn = QPushButton("On my way")
        self.quick_on_way_btn.clicked.connect(
            lambda: self._send_quick_message("On my way")
        )

        self.quick_two_min_btn = QPushButton("2 minutes away")
        self.quick_two_min_btn.clicked.connect(
            lambda: self._send_quick_message("2 minutes away")
        )

        self.quick_arrived_btn = QPushButton("I arrived")
        self.quick_arrived_btn.clicked.connect(
            lambda: self._send_quick_message("I arrived")
        )

        quick_row.addWidget(self.quick_on_way_btn)
        quick_row.addWidget(self.quick_two_min_btn)
        quick_row.addWidget(self.quick_arrived_btn)
        quick_row.addStretch()

        layout.addWidget(self.chat_box)
        layout.addWidget(self.chat_input)
        layout.addWidget(self.chat_send)
        layout.addLayout(quick_row)

        # Typing indicator label
        self.typing_label = QLabel("")
        self.typing_label.setAlignment(Qt.AlignLeft)
        self.typing_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.typing_label)

        # History + stats + profile + theme + weather + scheduled + logout
        bottom_row = QHBoxLayout()
        self.history_btn = QPushButton("View history")
        self.history_btn.clicked.connect(self.main_window.show_ride_history)

        self.stats_btn = QPushButton("My stats")
        self.stats_btn.clicked.connect(self.main_window.show_stats_page)

        self.profile_btn = QPushButton("Profile")
        self.profile_btn.clicked.connect(self._show_profile)

        self.theme_btn = QPushButton("Theme")
        self.theme_btn.clicked.connect(self.main_window.show_theme_settings)

        self.weather_btn = QPushButton("Weather")
        self.weather_btn.clicked.connect(self._show_weather)

        # Scheduled rides view
        self.scheduled_btn = QPushButton("Scheduled rides")
        self.scheduled_btn.clicked.connect(self._show_scheduled_rides)

        self.logout_btn = QPushButton("Logout")
        self.logout_btn.clicked.connect(self.main_window.logout)

        bottom_row.addWidget(self.history_btn)
        bottom_row.addWidget(self.stats_btn)
        bottom_row.addWidget(self.profile_btn)
        bottom_row.addWidget(self.theme_btn)
        bottom_row.addWidget(self.weather_btn)
        bottom_row.addWidget(self.scheduled_btn)   # NEW
        bottom_row.addStretch()
        bottom_row.addWidget(self.logout_btn)
        layout.addLayout(bottom_row)

        layout.addStretch()

    def refresh_ui(self):
        uname = self.main_window.current_username or "?"
        area = self.main_window.current_area or "?"
        self.info_label.setText(f"Logged in as driver {uname} (area: {area})")
        self.status_label.setText(f"Status: {self.current_status}")
        self._on_refresh()

    def refresh_pending(self):
        self._on_refresh()

    #Profile
    def _show_profile(self):
        dlg = ProfileDialog(self.main_window, self)
        dlg.exec_()
        # Area / schedule / password might have changed
        self.refresh_ui()

    #Weather
    def _show_weather(self):
        """
         Default location is always Beirut unless the user changes it
        inside the weather window search box.
        """
        if self.weather_window is None:
            # Default city = Beirut
            self.weather_window = WeatherApp(default_location="Beirut")

        self.weather_window.show()
        self.weather_window.raise_()
        self.weather_window.activateWindow()

    #Scheduled rides view 

    def _show_scheduled_rides(self):
        dlg = ScheduledRidesDialog(self.main_window, role="driver", parent=self)
        dlg.exec_()

    # Status helpers 

    def _set_status_available(self):
        self._set_status("available")

    def _set_status_dnd(self):
        self._set_status("dnd")

    def _set_status(self, status: str):
        try:
            resp = self.main_window.api_client.set_status(status)
        except Exception as e:
            QMessageBox.critical(
                self, "Status error", f"Failed to update status:\n{e}"
            )
            return

        if resp.get("status") == "success":
            self.current_status = resp.get("status_value", status)
            self.status_label.setText(f"Status: {self.current_status}")
        else:
            QMessageBox.warning(
                self,
                "Status error",
                resp.get("message", "Could not update status."),
            )

    # Get selection 

    def _get_selected_ride_id_and_passenger(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No selection", "Please select a ride first.")
            return None, None

        id_item = self.table.item(row, 0)
        passenger_item = self.table.item(row, 1)
        if id_item is None or passenger_item is None:
            QMessageBox.warning(self, "Error", "Selected row is missing data.")
            return None, None

        try:
            ride_id = int(id_item.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid ride ID.")
            return None, None

        passenger = passenger_item.text()
        return ride_id, passenger

    #Handlers 
    def _on_refresh(self):
        area = self.main_window.current_area
        if not area:
            QMessageBox.warning(
                self,
                "Missing data",
                "Your area is not known. Please log out and log in again.",
            )
            return

        try:
            resp = self.main_window.api_client.get_pending_rides(area)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch rides:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self, "Error", resp.get("message", "Failed to fetch rides.")
            )
            return

        rides = resp.get("rides", [])
        self.table.setRowCount(len(rides))

        for row, ride in enumerate(rides):
            ride_id = ride.get("id")
            passenger = ride.get("passenger_username")
            area = ride.get("area")
            time_val = ride.get("time")
            weekday = ride.get("weekday")

            from gui.main import WEEKDAY_NAMES, seconds_to_hhmm  # avoid duplication

            time_str = seconds_to_hhmm(time_val)
            if isinstance(weekday, int) and 0 <= weekday < len(WEEKDAY_NAMES):
                weekday_str = WEEKDAY_NAMES[weekday]
            else:
                weekday_str = str(weekday)

            # fetch passenger rating
            rating_text = "N/A"
            try:
                r_resp = self.main_window.api_client.get_rating(passenger)
                if r_resp.get("status") == "success":
                    avg = r_resp.get("rating")
                    if avg is not None:
                        rating_text = f"{avg:.2f} ★"
            except Exception:
                pass

            self.table.setItem(row, 0, QTableWidgetItem(str(ride_id)))
            self.table.setItem(row, 1, QTableWidgetItem(str(passenger)))
            self.table.setItem(row, 2, QTableWidgetItem(str(area)))
            self.table.setItem(row, 3, QTableWidgetItem(time_str))
            self.table.setItem(row, 4, QTableWidgetItem(weekday_str))
            self.table.setItem(row, 5, QTableWidgetItem(rating_text))

    def _on_accept_selected(self):
        ride_id, passenger = self._get_selected_ride_id_and_passenger()
        if ride_id is None:
            return

        self.passenger_username = passenger
        self.current_ride_id = ride_id

        # dynamic P2P port
        port = random.randint(30000, 40000)

        # Start chat server
        if self.chat_server:
            self.chat_server.disconnect()
        self.chat_server = DriverChatServer(port)
        self.chat_server.received.connect(self._on_chat_received)
        self.chat_server.typing.connect(self._on_chat_typing_received)
        self.chat_server.disconnected.connect(self._on_chat_disconnected)
        self.chat_server.start()

        # Tell backend we accept the ride with IP/port
        try:
            resp = self.main_window.api_client.accept_ride(
                ride_id=ride_id,
                driver_username=self.main_window.current_username,
                driver_ip="127.0.0.1",
                driver_port=port,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to accept ride:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self, "Error", resp.get("message", "Failed to accept ride.")
            )
            return

        self.chat_box.append(
            f"[{_now_hhmm()}] [System] Ride {ride_id} accepted. Chat server listening on port {port}."
        )
        self.complete_btn.setEnabled(True)

    def _on_decline_selected(self):
        ride_id, _ = self._get_selected_ride_id_and_passenger()
        if ride_id is None:
            return

        try:
            resp = self.main_window.api_client.decline_ride(ride_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to decline ride:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self,
                "Error",
                resp.get("message", "Could not decline the ride."),
            )
            return

        self.chat_box.append(f"[{_now_hhmm()}] [System] Ride {ride_id} declined.")
        self._on_refresh()

    def _on_complete_ride(self):
        if not self.current_ride_id or not self.passenger_username:
            QMessageBox.warning(
                self, "No active ride", "There is no active ride to complete."
            )
            return

        try:
            resp = self.main_window.api_client.complete_ride(self.current_ride_id)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to complete ride:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self,
                "Error",
                resp.get("message", "Could not complete the ride."),
            )
            return

        # Ask driver to rate passenger
        dlg = RatingDialog(self, who_label=f"passenger {self.passenger_username}")
        if dlg.exec_() == RatingDialog.Accepted:
            score = dlg.rating
            comment = dlg.comment
            try:
                self.main_window.api_client.submit_rating(
                    ride_id=self.current_ride_id,
                    rater_username=self.main_window.current_username,
                    ratee_username=self.passenger_username,
                    score=score,
                    comment=comment,
                )
            except Exception as e:
                QMessageBox.warning(
                    self, "Rating error", f"Could not submit rating:\n{e}"
                )
        """
        Disconnect chat after ride completion so passenger gets a disconnect event and is prompted to rate the driver,
        and they can no longer chat after the ride.
        """
        if self.chat_server:
            try:
                self.chat_server.disconnect()
            except Exception:
                pass
            self.chat_server = None

        QMessageBox.information(self, "Ride completed", "Ride has been completed.")
        self.complete_btn.setEnabled(False)
        self.current_ride_id = None
        self.passenger_username = None
        self.chat_box.append(f"[{_now_hhmm()}] [System] Ride ended.")
        self._on_refresh()

    # Scheduled ride notifications 
    def handle_new_scheduled_ride(self, msg: dict):
        """
        Called by MainWindow when a 'scheduled_ride_created' notification arrives
        for this driver.

        Expected msg shape (best-effort):
          {
            "action": "scheduled_ride_created",
            "ride": {
                "id": ...,
                "passenger_username": ...,
                "area": ...,
                "date": "YYYY-MM-DD",
                "time": <seconds or "HH:MM">,
                ...
            }
          }
        """
        ride = msg.get("ride") or msg
        ride_id = ride.get("id") or ride.get("ride_id")
        passenger = ride.get("passenger_username", "")
        area = ride.get("area", "")
        date = ride.get("date", "")
        time_val = ride.get("time", "")
        if isinstance(time_val, int):
            from gui.main import seconds_to_hhmm  # reuse existing helper
            time_str = seconds_to_hhmm(time_val)
        else:
            time_str = str(time_val)

        text = (
            f"You have a new scheduled ride request.\n\n"
            f"ID: {ride_id}\n"
            f"Passenger: {passenger}\n"
            f"Area: {area}\n"
            f"Date: {date}\n"
            f"Time: {time_str}\n\n"
            f"Open 'Scheduled rides' to accept or decline."
        )
        QMessageBox.information(self, "New scheduled ride", text)

    def handle_scheduled_ride_updated(self, msg: dict):
        """
        Called by MainWindow when a 'scheduled_ride_updated' notification arrives
        for this driver, typically when a passenger cancels.
        msg shape:
          {
            "action": "scheduled_ride_updated",
            "ride_id": ...,
            "status": "canceled" | ...
          }
        """
        ride_id = msg.get("ride_id") or msg.get("id")
        status = msg.get("status") or msg.get("new_status")

        if ride_id is None or not status:
            return

        if status in ("canceled", "cancelled"):
            text = f"Passenger canceled scheduled ride (ID {ride_id})."
        else:
            text = f"Scheduled ride (ID {ride_id}) status changed to: {status}"

        QMessageBox.information(self, "Scheduled ride update", text)

    #  chat hooks 
    def _on_chat_received(self, msg: str):
        # Use the real passenger username if we know it, otherwise fall back
        name = self.passenger_username or "Passenger"
        self.chat_box.append(f"[{_now_hhmm()}] [{name}] {msg.strip()}")

    def _send_chat(self):
        msg = self.chat_input.text().strip()
        if not msg:
            return

        # Only send if the chat server and its client socket are connected
        if self.chat_server and self.chat_server.client_sock:
            self.chat_server.send(msg)
            self.chat_box.append(f"[{_now_hhmm()}] [You] {msg}")
            self.chat_input.clear()
        else:
            QMessageBox.information(
                self, "No chat", "Chat is not connected to a passenger yet."
            )

    def _send_quick_message(self, text: str):
        """Send a predefined quick message."""
        if not (self.chat_server and self.chat_server.client_sock):
            QMessageBox.information(
                self, "No chat", "Chat is not connected to a passenger yet."
            )
            return
        self.chat_server.send(text)
        self.chat_box.append(f"[{_now_hhmm()}] [You] {text}")

    def _on_chat_disconnected(self):
        self.chat_box.append(f"[{_now_hhmm()}] [System] Chat disconnected.")
        if self.chat_server:
            self.chat_server = None

    def _on_chat_typing(self, _text: str):
        """
        Called by MainWindowwhenever the driver edits the chat input.
        Rate-limit typing notifications.
        """
        import time as _time

        now = _time.time()
        if self._last_typing_sent_ts is None or now - self._last_typing_sent_ts > 1.0:
            self._last_typing_sent_ts = now
            if self.chat_server:
                self.chat_server.send_typing()

    def _on_chat_typing_received(self):
        """Show 'Passenger is typing...' for a short time."""
        self.typing_label.setText("Passenger is typing...")
        if self._typing_timer is None:
            self._typing_timer = QTimer(self)
            self._typing_timer.setSingleShot(True)
            self._typing_timer.timeout.connect(
                lambda: self.typing_label.setText("")
            )
        self._typing_timer.start(2000)
