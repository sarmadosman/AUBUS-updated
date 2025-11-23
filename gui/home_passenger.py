from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QHBoxLayout,
    QTimeEdit,
    QDateEdit,
    QMessageBox,
    QTextEdit,
    QLineEdit,
    QCheckBox,
    QComboBox,
)
from PyQt5.QtCore import Qt, QTime, QDate, QThread, pyqtSignal, QTimer
import socket
from datetime import datetime
import time as _time

from gui.rating_dialog import RatingDialog
from gui.weather import WeatherApp
from gui.profile_dialog import ProfileDialog   # Profile editor dialog
from gui.scheduled_rides_dialog import ScheduledRidesDialog  # "My scheduled rides"


def _now_hhmm() -> str:
    """Return current time as HH:MM for compact chat timestamps."""
    t = datetime.now().time()
    return f"{t.hour:02d}:{t.minute:02d}"


class PassengerChatClient(QThread):
    received = pyqtSignal(str)
    typing = pyqtSignal()          # typing indicator from driver
    disconnected = pyqtSignal()

    def __init__(self, ip: str, port: int, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.port = port
        self.sock = None
        self._running = True

    def run(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.ip, self.port))
            while self._running:
                data = self.sock.recv(1024)
                if not data:
                    break
                text = data.decode("utf-8")
                if text.strip() == "__TYPING__":  # special control packet
                    self.typing.emit()
                    continue
                self.received.emit(text)
        except Exception:
            pass
        finally:
            self._close()

    def send(self, msg: str):
        try:
            if self.sock:
                self.sock.send(msg.encode("utf-8"))
        except Exception:
            pass

    def send_typing(self):
        """Send a small control message to indicate typing to the driver."""
        try:
            if self.sock:
                self.sock.send(b"__TYPING__")
        except Exception:
            pass

    def disconnect(self):
        self._running = False
        self._close()

    def _close(self):
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.disconnected.emit()


class HomePassenger(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window

        self.chat_client: PassengerChatClient | None = None
        self.chat_connected = False

        self.current_ride_id = None
        self.driver_username = None
        self.last_accepted_ride = None
        self._rating_shown_for_ride = False  # ensure rating dialog only once

        # Premium: preferred driver selection
        self.selected_driver_username = None
        self._last_driver_list = []  # cached list from last search

        # Weather window
        self.weather_window: WeatherApp | None = None

        # Typing indicator timer
        self._typing_timer: QTimer | None = None

        # For rate-limiting typing notifications
        self._last_typing_sent_ts: float | None = None

        self._build_ui()

    def shutdown(self):
        """
        Stop the passenger chat client thread cleanly (if running).
        Called from MainWindow on logout / app exit.
        """
        if self.chat_client:
            try:
                self.chat_client.disconnect()
                # Wait up to 2 seconds for the QThread to finish
                self.chat_client.wait(2000)
            except Exception:
                pass
            self.chat_client = None

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignTop)

        self.title_label = QLabel("Passenger Home")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 20px; font-weight: bold;")

        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.info_label)

        # --- Request ride *today* section ---
        ride_box = QVBoxLayout()

        ride_label = QLabel("Get a ride now (today)")
        ride_label.setAlignment(Qt.AlignCenter)
        ride_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        ride_box.addWidget(ride_label)

        time_row = QHBoxLayout()
        time_lbl = QLabel("Pickup time (today):")
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime.currentTime())
        time_row.addWidget(time_lbl)
        time_row.addWidget(self.time_edit)

        # Preferred-only toggle
        self.preferred_only_checkbox = QCheckBox("Preferred driver only")
        self.preferred_only_checkbox.setToolTip(
            "If checked, your ride will only be matched to your preferred driver.\n"
            "If they are not online/available, the request will fail."
        )
        time_row.addWidget(self.preferred_only_checkbox)

        ride_box.addLayout(time_row)

        self.request_btn = QPushButton("Request Ride (today)")
        self.request_btn.clicked.connect(self._on_request_ride)
        ride_box.addWidget(self.request_btn, alignment=Qt.AlignCenter)

        layout.addLayout(ride_box)

        # --- Schedule future ride section ---
        sched_box = QVBoxLayout()

        sched_label = QLabel("Schedule a future ride with a specific driver")
        sched_label.setAlignment(Qt.AlignCenter)
        sched_label.setStyleSheet("font-size: 16px; font-weight: bold; margin-top: 10px;")
        sched_box.addWidget(sched_label)

        sched_row1 = QHBoxLayout()
        date_lbl = QLabel("Date:")
        self.sched_date_edit = QDateEdit()
        self.sched_date_edit.setCalendarPopup(True)
        self.sched_date_edit.setDate(QDate.currentDate())

        time2_lbl = QLabel("Time:")
        self.sched_time_edit = QTimeEdit()
        self.sched_time_edit.setDisplayFormat("HH:mm")
        self.sched_time_edit.setTime(QTime.currentTime())

        sched_row1.addWidget(date_lbl)
        sched_row1.addWidget(self.sched_date_edit)
        sched_row1.addWidget(time2_lbl)
        sched_row1.addWidget(self.sched_time_edit)
        sched_box.addLayout(sched_row1)

        sched_row2 = QHBoxLayout()
        driver_lbl = QLabel("Driver username:")
        self.sched_driver_edit = QLineEdit()
        self.sched_driver_edit.setPlaceholderText("Exact driver username (required)")
        sched_row2.addWidget(driver_lbl)
        sched_row2.addWidget(self.sched_driver_edit)
        sched_box.addLayout(sched_row2)

        self.sched_btn = QPushButton("Schedule ride")
        self.sched_btn.clicked.connect(self._on_schedule_ride)
        sched_box.addWidget(self.sched_btn, alignment=Qt.AlignCenter)

        layout.addLayout(sched_box)

        # --- Premium: browse / select drivers ---
        drivers_box = QVBoxLayout()

        drivers_label = QLabel("Browse drivers")
        drivers_label.setAlignment(Qt.AlignCenter)
        drivers_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        drivers_box.addWidget(drivers_label)

        # Area filter + search
        area_row = QHBoxLayout()
        area_lbl = QLabel("Area:")
        self.driver_area_edit = QLineEdit()
        self.driver_area_edit.setPlaceholderText("Leave empty for all drivers")
        area_row.addWidget(area_lbl)
        area_row.addWidget(self.driver_area_edit)

        self.search_drivers_btn = QPushButton("Search")
        self.search_drivers_btn.clicked.connect(self._on_search_drivers)
        area_row.addWidget(self.search_drivers_btn)

        drivers_box.addLayout(area_row)

        # Sort options
        sort_row = QHBoxLayout()
        sort_lbl = QLabel("Sort by:")
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["Default", "Online first", "Highest rating"])
        self.sort_combo.currentIndexChanged.connect(self._apply_driver_sort_and_display)
        sort_row.addWidget(sort_lbl)
        sort_row.addWidget(self.sort_combo)
        sort_row.addStretch()
        drivers_box.addLayout(sort_row)

        # Current preferred driver
        self.preferred_driver_label = QLabel("Preferred driver: (none)")
        drivers_box.addWidget(self.preferred_driver_label)

        # Text list of drivers
        self.drivers_list_box = QTextEdit()
        self.drivers_list_box.setReadOnly(True)
        self.drivers_list_box.setPlaceholderText(
            "Click 'Search' to see drivers, their area, status, and average rating.\n"
            "Drivers shown here come from the server in realtime."
        )
        drivers_box.addWidget(self.drivers_list_box)

        # Select preferred driver by username
        select_row = QHBoxLayout()
        self.driver_username_edit = QLineEdit()
        self.driver_username_edit.setPlaceholderText("Type driver username to select")
        self.set_preferred_btn = QPushButton("Set preferred")
        self.set_preferred_btn.clicked.connect(self._on_set_preferred_from_text)
        self.clear_preferred_btn = QPushButton("Clear")
        self.clear_preferred_btn.clicked.connect(self._on_clear_preferred_driver)

        select_row.addWidget(self.driver_username_edit)
        select_row.addWidget(self.set_preferred_btn)
        select_row.addWidget(self.clear_preferred_btn)
        drivers_box.addLayout(select_row)

        layout.addLayout(drivers_box)

        # --- Chat UI ---
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

        self.quick_here_btn = QPushButton("I'm here")
        self.quick_here_btn.clicked.connect(
            lambda: self._send_quick_message("I'm here")
        )

        self.quick_thanks_btn = QPushButton("Thank you!")
        self.quick_thanks_btn.clicked.connect(
            lambda: self._send_quick_message("Thank you!")
        )

        quick_row.addWidget(self.quick_on_way_btn)
        quick_row.addWidget(self.quick_here_btn)
        quick_row.addWidget(self.quick_thanks_btn)
        quick_row.addStretch()

        layout.addWidget(self.chat_box)
        layout.addWidget(self.chat_input)
        layout.addWidget(self.chat_send)
        layout.addLayout(quick_row)

        # Typing indicator
        self.typing_label = QLabel("")
        self.typing_label.setAlignment(Qt.AlignLeft)
        self.typing_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.typing_label)

        # --- History + stats + profile + theme + weather + scheduled + logout ---
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
        bottom_row.addWidget(self.scheduled_btn)
        bottom_row.addStretch()
        bottom_row.addWidget(self.logout_btn)
        layout.addLayout(bottom_row)

        layout.addStretch()

    def refresh_ui(self):
        uname = self.main_window.current_username or "?"
        area = self.main_window.current_area or "?"
        self.info_label.setText(f"Logged in as passenger {uname} (area: {area})")

        # Prefill area filter with current area if empty
        if self.main_window.current_area and not self.driver_area_edit.text().strip():
            self.driver_area_edit.setText(self.main_window.current_area)

        # Load preferred driver from preferences (if any)
        prefs = getattr(self.main_window.api_client, "preferences", None) or {}
        preferred = prefs.get("preferred_driver_username")

        self.selected_driver_username = preferred
        if preferred:
            self.preferred_driver_label.setText(f"Preferred driver: {preferred}")
            self.driver_username_edit.setText(preferred)
            # Also suggest it in the scheduled-driver field if empty
            if not self.sched_driver_edit.text().strip():
                self.sched_driver_edit.setText(preferred)
        else:
            self.preferred_driver_label.setText("Preferred driver: (none)")

    # ---------------- weather ----------------

    def _show_weather(self):
        if self.weather_window is None:
            self.weather_window = WeatherApp(default_location="Beirut")

        self.weather_window.show()
        self.weather_window.raise_()
        self.weather_window.activateWindow()

    # ---------------- scheduled rides view ----------------

    def _show_scheduled_rides(self):
        dlg = ScheduledRidesDialog(self.main_window, role="passenger", parent=self)
        dlg.exec_()

    # ---------------- profile ----------------

    def _show_profile(self):
        dlg = ProfileDialog(self.main_window, self)
        dlg.exec_()
        # Area / schedule / password might have changed; reflect area in label + filters
        self.refresh_ui()

    # ---------------- request ride TODAY ----------------

    def _on_request_ride(self):
        uname = self.main_window.current_username
        area = self.main_window.current_area

        if not uname or not area:
            QMessageBox.critical(
                self,
                "Not logged in",
                "Missing user or area information. Please log out and log in again.",
            )
            return

        t = self.time_edit.time()
        time_str = f"{t.hour():02d}:{t.minute():02d}"

        preferred_only = self.preferred_only_checkbox.isChecked()

        client = self.main_window.api_client
        try:
            resp = client.create_ride(
                passenger_username=uname,
                area=area,
                time_str=time_str,
                target_driver_username=self.selected_driver_username,
                preferred_only=preferred_only,
            )
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to contact server:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(self, "Error", resp.get("message", "Unknown error."))
            return

        self.current_ride_id = resp.get("ride_id")
        self._rating_shown_for_ride = False
        QMessageBox.information(
            self, "Requested", f"Ride {self.current_ride_id} created."
        )

    # ---------------- schedule FUTURE ride ----------------

    def _on_schedule_ride(self):
        uname = self.main_window.current_username
        area = self.main_window.current_area

        if not uname or not area:
            QMessageBox.critical(
                self,
                "Not logged in",
                "Missing user or area information. Please log out and log in again.",
            )
            return

        date = self.sched_date_edit.date()
        time = self.sched_time_edit.time()
        date_str = date.toString("yyyy-MM-dd")
        time_str = f"{time.hour():02d}:{time.minute():02d}"

        driver_username = self.sched_driver_edit.text().strip()
        if not driver_username:
            QMessageBox.warning(
                self,
                "Missing driver",
                "Please enter the driver username for this scheduled ride.",
            )
            return

        client = self.main_window.api_client
        try:
            resp = client.create_scheduled_ride(
                passenger_username=uname,
                driver_username=driver_username,
                area=area,
                date_str=date_str,
                time_str=time_str,
            )
        except AttributeError:
            QMessageBox.critical(
                self,
                "Not implemented",
                "The client API is missing create_scheduled_ride().\n"
                "Please make sure client/api_client.py is updated.",
            )
            return
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to contact server for scheduled ride:\n{e}",
            )
            return

        if resp.get("status") != "success":
            QMessageBox.critical(
                self,
                "Error",
                resp.get("message", "Failed to schedule ride."),
            )
            return

        ride_id = resp.get("ride_id")
        QMessageBox.information(
            self,
            "Scheduled",
            (
                f"Scheduled ride created (ID {ride_id}).\n"
                "You can manage it from the 'Scheduled rides' view."
            ),
        )

    # ---------------- premium: browse/select drivers ----------------

    def _on_search_drivers(self):
        area_filter = self.driver_area_edit.text().strip()
        if not area_filter:
            area_filter = None

        client = self.main_window.api_client
        try:
            resp = client.list_drivers(area_filter)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to contact server:\n{e}")
            return

        if resp.get("status") != "success":
            QMessageBox.critical(self, "Error", resp.get("message", "Unknown error."))
            return

        drivers = resp.get("drivers", []) or []
        self._last_driver_list = drivers

        self._apply_driver_sort_and_display()

    def _apply_driver_sort_and_display(self):
        drivers = list(self._last_driver_list or [])
        if not drivers:
            self.drivers_list_box.setPlainText("No drivers found for this area.")
            return

        mode = self.sort_combo.currentText()

        if mode == "Online first":
            drivers.sort(key=lambda d: (not d.get("online", False)))
        elif mode == "Highest rating":

            def rating_key(d):
                r = d.get("rating")
                return -(r if isinstance(r, (int, float)) else 0.0)

            drivers.sort(key=rating_key)

        lines = []
        preferred = self.selected_driver_username
        for d in drivers:
            username = d.get("username", "")
            name = d.get("name", "")
            area_val = d.get("area", "")
            rating = d.get("rating")
            status = d.get("status", "")
            online = d.get("online", False)

            if rating is None:
                rating_text = "N/A"
            else:
                rating_text = f"{rating:.2f} ★"

            online_text = "online" if online else "offline"
            if status and status not in ("offline",):
                status_text = f"{online_text}, {status}"
            else:
                status_text = online_text

            pref_tag = "  ★ preferred" if preferred and username == preferred else ""
            lines.append(
                f"{username}  |  {name}  |  area: {area_val}  |  rating: {rating_text}  |  {status_text}{pref_tag}"
            )

        self.drivers_list_box.setPlainText("\n".join(lines))

    def _on_set_preferred_from_text(self):
        username = self.driver_username_edit.text().strip()
        if not username:
            QMessageBox.warning(self, "No username", "Please type a driver username.")
            return

        if self._last_driver_list:
            valid_usernames = {d.get("username") for d in self._last_driver_list}
            if username not in valid_usernames:
                res = QMessageBox.question(
                    self,
                    "Unknown driver",
                    "This username was not in the last search results.\n"
                    "Do you still want to set it as preferred?",
                )
                if res != QMessageBox.Yes:
                    return

        self.selected_driver_username = username
        self.preferred_driver_label.setText(f"Preferred driver: {username}")

        client = self.main_window.api_client
        prefs = client.preferences or {}
        new_prefs = dict(prefs)
        new_prefs["preferred_driver_username"] = username
        try:
            resp = client.save_preferences(None, new_prefs)
            if resp.get("status") != "success":
                QMessageBox.warning(
                    self,
                    "Preferences",
                    "Preferred driver set locally, but saving to server failed.",
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Preferences",
                f"Preferred driver set locally, but saving to server failed:\n{e}",
            )

        # Also fill the scheduled-driver field if empty
        if not self.sched_driver_edit.text().strip():
            self.sched_driver_edit.setText(username)

        QMessageBox.information(
            self,
            "Preferred driver set",
            (
                "New rides will try to target driver "
                f"'{username}'. If you check 'Preferred driver only',\n"
                "rides will fail if that driver is unavailable."
            ),
        )

    def _on_clear_preferred_driver(self):
        # Remember previous preferred (if any) before clearing
        prev_preferred = self.selected_driver_username

        # Clear local state
        self.selected_driver_username = None
        self.preferred_driver_label.setText("Preferred driver: (none)")

        # Clear the manual username field
        self.driver_username_edit.clear()

        # If the scheduled-driver field was using the same preferred username,
        # clear it too so the UI fully reflects the change.
        if prev_preferred and self.sched_driver_edit.text().strip() == prev_preferred:
            self.sched_driver_edit.clear()

        # Persist to server preferences
        client = self.main_window.api_client
        prefs = client.preferences or {}
        new_prefs = dict(prefs)
        new_prefs["preferred_driver_username"] = None
        try:
            resp = client.save_preferences(None, new_prefs)
            if resp.get("status") != "success":
                QMessageBox.warning(
                    self,
                    "Preferences",
                    "Preferred driver cleared locally, but saving to server failed.",
                )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Preferences",
                f"Preferred driver cleared locally, but saving to server failed:\n{e}",
            )

        QMessageBox.information(self, "Preferred driver", "Cleared preferred driver.")


    # ---------------- realtime: ride accepted & completed ----------------

    def handle_ride_accepted(self, msg: dict):
        """
        Called by MainWindow when a 'ride_accepted' notification arrives.
        msg: ride_id, driver_username, driver_ip, driver_port, driver_rating
        """
        self.last_accepted_ride = msg
        self.current_ride_id = msg.get("ride_id")
        self.driver_username = msg.get("driver_username")
        ip = msg.get("driver_ip")
        port = msg.get("driver_port")
        driver_rating_text = msg.get("driver_rating", "N/A")

        QMessageBox.information(
            self,
            "Ride accepted",
            (
                f"Your ride (ID {self.current_ride_id}) was accepted!\n\n"
                f"Driver: {self.driver_username}\n"
                f"Driver rating: {driver_rating_text}\n"
                f"IP: {ip}\nPort: {port}\n\n"
                f"Chat will now connect."
            ),
        )

        if self.chat_client:
            self.chat_client.disconnect()

        self.chat_client = PassengerChatClient(ip, port)
        self.chat_client.received.connect(self._on_chat_received)
        self.chat_client.typing.connect(self._on_chat_typing_received)
        self.chat_client.disconnected.connect(self._on_chat_disconnected)
        self.chat_client.start()
        self.chat_connected = True

        self.chat_box.append(
            f"[{_now_hhmm()}] [System] Driver {self.driver_username} accepted your ride. Chat started."
        )

    def handle_ride_completed(self, msg: dict):
        """
        Called by MainWindow when 'ride_completed' notification arrives.
        This is the correct moment to prompt the PASSENGER for a rating.
        """
        if self._rating_shown_for_ride:
            return  # already handled

        ride_id = msg.get("ride_id") or self.current_ride_id
        driver_username = msg.get("driver_username") or self.driver_username

        if not ride_id or not driver_username:
            # Fallback: just inform
            QMessageBox.information(
                self,
                "Ride completed",
                "Your ride has been marked as completed.",
            )
            return

        self._rating_shown_for_ride = True

        dlg = RatingDialog(self, who_label=f"driver {driver_username}")
        if dlg.exec_() == RatingDialog.Accepted:
            score = dlg.rating
            comment = dlg.comment
            try:
                self.main_window.api_client.submit_rating(
                    ride_id=ride_id,
                    rater_username=self.main_window.current_username,
                    ratee_username=driver_username,
                    score=score,
                    comment=comment,
                )
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Rating error",
                    f"Could not submit rating:\n{e}",
                )

        QMessageBox.information(
            self, "Ride ended", "Your ride has ended. Thank you for your rating!"
        )

        # Reset ride state
        self.current_ride_id = None
        self.driver_username = None
        self.last_accepted_ride = None

    # ---------------- scheduled ride notifications ----------------

    def handle_scheduled_ride_updated(self, msg: dict):
        """
        Called by MainWindow when a 'scheduled_ride_updated' notification arrives
        for this passenger. This is used when a driver accepts/declines a
        scheduled ride, or if it is otherwise updated.
        Expected msg shape (best-effort):
          {
            "action": "scheduled_ride_updated",
            "ride_id": ...,
            "status": "accepted" | "declined" | "cancelled" | ...
          }
        """
        ride_id = msg.get("ride_id") or msg.get("id")
        status = msg.get("status") or msg.get("new_status")

        if ride_id is None or not status:
            return

        if status == "accepted":
            text = f"Your scheduled ride (ID {ride_id}) was accepted by the driver."
        elif status == "declined":
            text = f"Your scheduled ride (ID {ride_id}) was declined by the driver."
        elif status in ("canceled", "cancelled"):
            text = f"Your scheduled ride (ID {ride_id}) was canceled."
        else:
            text = f"Your scheduled ride (ID {ride_id}) status changed to: {status}"

        QMessageBox.information(self, "Scheduled ride update", text)

    # chat hooks
    def _on_chat_received(self, msg: str):
        # Use the real driver username if we know it, otherwise fall back
        name = self.driver_username or "Driver"
        self.chat_box.append(f"[{_now_hhmm()}] [{name}] {msg.strip()}")

    def _send_chat(self):
        msg = self.chat_input.text().strip()
        if not msg:
            return
        if self.chat_client:
            self.chat_client.send(msg)
            self.chat_box.append(f"[{_now_hhmm()}] [You] {msg}")
            self.chat_input.clear()

    def _send_quick_message(self, text: str):
        if self.chat_client is None:
            QMessageBox.information(
                self, "No chat", "Chat is not connected to a driver yet."
            )
            return
        self.chat_client.send(text)
        self.chat_box.append(f"[{_now_hhmm()}] [You] {text}")

    def _on_chat_disconnected(self):
        """
        Chat ended – just show a system message.
        Rating is now triggered ONLY by the 'ride_completed' notification.
        """
        self.chat_connected = False
        self.chat_box.append(f"[{_now_hhmm()}] [System] Chat disconnected.")

    def _on_chat_typing(self, _text: str):
        now = _time.time()
        if self._last_typing_sent_ts is None or now - self._last_typing_sent_ts > 1.0:
            self._last_typing_sent_ts = now
            if self.chat_client:
                self.chat_client.send_typing()

    def _on_chat_typing_received(self):
        self.typing_label.setText("Driver is typing...")
        if self._typing_timer is None:
            self._typing_timer = QTimer(self)
            self._typing_timer.setSingleShot(True)
            self._typing_timer.timeout.connect(
                lambda: self.typing_label.setText("")
            )
        self._typing_timer.start(2000)
