import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QStackedWidget, QMessageBox
from PyQt5.QtCore import QTimer

from client.api_client import RealtimeClient

from gui.login import LoginPage
from gui.signup import SignupPage
from gui.home_passenger import HomePassenger
from gui.home_driver import HomeDriver
from gui.ride_history import RideHistoryPage
from gui.theme_settings import ThemeSettingsPage   # premium
from gui.stats_page import StatsPage               # premium 


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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("AUBus")
        self.resize(900, 600)

        # Shared realtime client (persistent socket + listener thread)
        self.api_client = RealtimeClient()

        # Current user info
        self.current_username = None
        self.current_role = None
        self.current_area = None
        self.current_preferences = {}

        # Pending notifications from background thread
        self._pending_driver_notifications = []          # "new_ride"
        self._pending_passenger_notifications = []       # "ride_accepted"
        self._pending_ride_declined_notifications = []   # "ride_declined"
        self._pending_ride_completed_notifications = []  # "ride_completed"
        self._pending_other_notifications = []


        self.notification_timer = QTimer(self)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_page = LoginPage(self)
        self.signup_page = SignupPage(self)
        self.home_passenger = HomePassenger(self)
        self.home_driver = HomeDriver(self)
        self.ride_history_page = RideHistoryPage(self)
        self.theme_settings_page = ThemeSettingsPage(self)
        self.stats_page = StatsPage(self)

        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.signup_page)
        self.stack.addWidget(self.home_passenger)
        self.stack.addWidget(self.home_driver)
        self.stack.addWidget(self.ride_history_page)
        self.stack.addWidget(self.theme_settings_page)
        self.stack.addWidget(self.stats_page)

        self.show_login()

        # Timer to process notifications from RealtimeClient in GUI thread
        self._notif_timer = QTimer(self)
        self._notif_timer.timeout.connect(self._process_notifications)
        self._notif_timer.start(300)

        # Apply default theme on startup
        self.apply_theme_from_preferences()

    # Theme handling (basic light/dark)

    def apply_theme_from_preferences(self):
        """
        Read theme from current_preferences (or api_client.preferences)
        and apply it. Defaults to 'default' (light / system style).
        """
        prefs = self.current_preferences or {}
        if not prefs:
            # try from realtime client if login already happened
            if self.api_client and getattr(self.api_client, "preferences", None):
                prefs = self.api_client.preferences or {}
        theme = prefs.get("theme") or prefs.get("theme_name") or "default"
        self.apply_theme(theme_name=theme, save_to_server=False)

    def apply_theme(self, theme_name: str, save_to_server: bool = True):
        """
        Apply a basic theme via Qt stylesheets.

        theme_name:
          - 'dark'   → dark UI
          - 'light'  → reset to default / light (empty stylesheet)
          - 'default'→ same as 'light'
        """
        from PyQt5.QtWidgets import QApplication

        if theme_name not in ("dark", "light", "default"):
            theme_name = "default"

        # Remember in local preferences
        self.current_preferences["theme"] = theme_name
        self.current_preferences["theme_name"] = theme_name

        app = QApplication.instance()
        if app is None:
            return

        if theme_name == "dark":
            # Simple dark style
            style = """
            QMainWindow {
                background-color: #2C3E50;
                color: #ECF0F1;
            }
            QWidget {
                background-color: #34495E;
                color: #ECF0F1;
            }
            QPushButton {
                background-color: #2C3E50;
                color: #ECF0F1;
                border-radius: 4px;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #3D566E;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QComboBox {
                background-color: #ECF0F1;
                color: #2C3E50;
                border: 1px solid #BDC3C7;
                border-radius: 3px;
                padding: 2px 4px;
            }
            QTableWidget {
                background-color: #ECF0F1;
                color: #2C3E50;
                gridline-color: #95A5A6;
            }
            QHeaderView::section {
                background-color: #2C3E50;
                color: #ECF0F1;
                padding: 2px;
                font-weight: bold;
            }
            """
        else:
            # Light / default → no global stylesheet, use system theme
            style = ""

        app.setStyleSheet(style)

        # Optionally persist theme to server preferences
        if save_to_server and self.current_username:
            try:
                prefs = dict(self.current_preferences)
                prefs["theme"] = theme_name
                prefs["theme_name"] = theme_name
                self.api_client.save_preferences(self.current_username, prefs)
            except Exception as e:
                print(f"[WARN] Failed to save theme preference: {e}")

    # Navigation

    def show_login(self):
        self.stack.setCurrentWidget(self.login_page)

    def show_signup(self):
        self.stack.setCurrentWidget(self.signup_page)

    def show_passenger_home(self):
        self.home_passenger.refresh_ui()
        self.stack.setCurrentWidget(self.home_passenger)

    def show_driver_home(self):
        self.home_driver.refresh_ui()
        self.stack.setCurrentWidget(self.home_driver)

    def show_ride_history(self):
        """
        Called from HomePassenger/HomeDriver "View history" button.
        Lets RideHistoryPage fetch and show ride history itself.
        """
        if not self.current_username or not self.current_role:
            QMessageBox.warning(self, "Not logged in", "Please log in first.")
            return

        self.ride_history_page.refresh_ui()
        self.stack.setCurrentWidget(self.ride_history_page)

    def show_theme_settings(self):
        self.theme_settings_page.refresh_ui()
        self.stack.setCurrentWidget(self.theme_settings_page)

    def show_stats_page(self):
        self.stats_page.refresh_ui()
        self.stack.setCurrentWidget(self.stats_page)

    # Login / Logout / Signup

    def attempt_login(self, username: str, password: str):
        """
        Called from LoginPage. Uses RealtimeClient to log in and
        start the background listener thread.
        """
        resp = self.api_client.connect_and_login(username, password)
        if resp.get("status") != "success":
            return resp

        self.current_username = resp.get("username", username)
        self.current_role = resp.get("role")
        self.current_area = resp.get("area")
        self.current_preferences = resp.get("preferences", {}) or {}

        # Apply theme from preferences
        self.apply_theme_from_preferences()

        # Wire realtime callbacks based on role
        self.api_client.on_new_ride = None
        self.api_client.on_ride_accepted = None
        self.api_client.on_ride_declined = None
        self.api_client.on_ride_completed = None
        self.api_client.on_other_notification = None

        if self.current_role == "driver":
            self.api_client.on_new_ride = self.handle_new_ride_notification
        elif self.current_role == "passenger":
            self.api_client.on_ride_accepted = self.handle_ride_accepted_notification
            self.api_client.on_ride_declined = self.handle_ride_declined_notification
            self.api_client.on_ride_completed = self.handle_ride_completed_notification

        # catch-all for things like scheduled_ride_created/updated
        self.api_client.on_other_notification = self.handle_other_notification

        if self.current_role == "driver":
            self.show_driver_home()
        else:
            self.show_passenger_home()

        return resp

    def logout(self):
        # First, stop chat threads cleanly
        try:
            self.home_driver.shutdown()
        except Exception:
            pass
        try:
            self.home_passenger.shutdown()
        except Exception:
            pass

        uname = self.current_username
        try:
            if uname:
                self.api_client.disconnect()
            else:
                self.api_client.close()
        except Exception:
            pass

        # Reset everything
        self.api_client = RealtimeClient()
        self.current_username = None
        self.current_role = None
        self.current_area = None
        self.current_preferences = {}
        self._pending_driver_notifications.clear()
        self._pending_passenger_notifications.clear()
        self._pending_ride_declined_notifications.clear()
        self._pending_ride_completed_notifications.clear()
        self._pending_other_notifications.clear()

        # Reset theme to default (light/system)
        self.apply_theme("default", save_to_server=False)

        self.show_login()

    def register_user(
        self,
        username: str,
        password: str,
        area: str,
        role: str,
        name: str,
        email: str,
        weekly_schedule: dict,
    ):
        """
        Called from SignupPage to create a user.
        """
        return self.api_client.register_user(
            username=username,
            password=password,
            area=area,
            role=role,
            name=name,
            email=email,
            weekly_schedule=weekly_schedule,
        )

    # Realtime notification handlers

    def handle_new_ride_notification(self, msg: dict):
        """Driver: 'new_ride'."""
        self._pending_driver_notifications.append(msg)

    def handle_ride_accepted_notification(self, msg: dict):
        """Passenger: 'ride_accepted'."""
        self._pending_passenger_notifications.append(msg)

    def handle_ride_declined_notification(self, msg: dict):
        """Passenger: 'ride_declined'."""
        self._pending_ride_declined_notifications.append(msg)

    def handle_ride_completed_notification(self, msg: dict):
        """Passenger: 'ride_completed' – trigger rating on passenger side."""
        self._pending_ride_completed_notifications.append(msg)

    def handle_other_notification(self, msg: dict):
        """
        Catch-all for notifications that RealtimeClient doesn't map to a
        dedicated callback, e.g. scheduled_ride_created / scheduled_ride_updated.
        """
        self._pending_other_notifications.append(msg)

    # Process notifications on GUI thread
    def _process_notifications(self):
        # Driver: new ride requests
        while self._pending_driver_notifications:
            msg = self._pending_driver_notifications.pop(0)

            ride_id = msg.get("ride_id")
            passenger = msg.get("passenger_username")
            area = msg.get("area")
            time_val = msg.get("time")
            weekday_int = msg.get("weekday")

            time_str = seconds_to_hhmm(time_val)
            if isinstance(weekday_int, int) and 0 <= weekday_int < 7:
                weekday_str = WEEKDAY_NAMES[weekday_int]
            else:
                weekday_str = str(weekday_int)

            # Fetch passenger's average rating
            rating_text = "N/A"
            try:
                r_resp = self.api_client.get_rating(passenger)
                if r_resp.get("status") == "success":
                    avg = r_resp.get("rating")
                    if avg is not None:
                        rating_text = f"{avg:.2f} ★"
            except Exception:
                pass

            text = (
                f"New ride request!\n\n"
                f"Ride ID: {ride_id}\n"
                f"Passenger: {passenger}\n"
                f"Passenger rating: {rating_text}\n"
                f"Area: {area}\n"
                f"Time: {time_str}\n"
                f"Weekday: {weekday_str}"
            )
            QMessageBox.information(self, "New ride", text)

            if self.current_role == "driver":
                try:
                    self.home_driver.refresh_pending()
                except Exception as e:
                    print(f"[WARN] Failed to refresh pending rides: {e}")

        # Passenger: ride accepted
        while self._pending_passenger_notifications:
            msg = self._pending_passenger_notifications.pop(0)

            driver_username = msg.get("driver_username")

            # Fetch driver's average rating for popup
            driver_rating_text = "N/A"
            try:
                r_resp = self.api_client.get_rating(driver_username)
                if r_resp.get("status") == "success":
                    avg = r_resp.get("rating")
                    if avg is not None:
                        driver_rating_text = f"{avg:.2f} ★"
            except Exception:
                pass

            msg["driver_rating"] = driver_rating_text

            try:
                self.home_passenger.handle_ride_accepted(msg)
            except Exception as e:
                print(f"[WARN] Failed to process ride_accepted in passenger home: {e}")

        # Passenger: ride declined
        while self._pending_ride_declined_notifications:
            msg = self._pending_ride_declined_notifications.pop(0)
            ride_id = msg.get("ride_id")
            driver_username = msg.get("driver_username") or "the driver"
            QMessageBox.information(
                self,
                "Ride declined",
                f"Your ride request (ID {ride_id}) was declined by {driver_username}.",
            )

        # Passenger: ride completed
        while self._pending_ride_completed_notifications:
            msg = self._pending_ride_completed_notifications.pop(0)
            try:
                self.home_passenger.handle_ride_completed(msg)
            except Exception as e:
                print(f"[WARN] Failed to process ride_completed in passenger home: {e}")

        # Other notifications: scheduled rides etc...
        while self._pending_other_notifications:
            msg = self._pending_other_notifications.pop(0)
            action = msg.get("action")

            if action == "scheduled_ride_created":
                # Only drivers care about this event
                if self.current_role == "driver":
                    try:
                        self.home_driver.handle_new_scheduled_ride(msg)
                    except Exception as e:
                        print(f"[WARN] Failed to handle 'scheduled_ride_created': {e}")

            elif action == "scheduled_ride_updated":
                try:
                    if self.current_role == "driver":
                        self.home_driver.handle_scheduled_ride_updated(msg)
                    elif self.current_role == "passenger":
                        self.home_passenger.handle_scheduled_ride_updated(msg)
                except Exception as e:
                    print(f"[WARN] Failed to handle 'scheduled_ride_updated': {e}")


    def closeEvent(self, event):
        """
        Ensure all QThreads (chat) are stopped before the window is destroyed,
        to avoid 'QThread: Destroyed while thread is still running'.
        """
        try:
            self.home_driver.shutdown()
        except Exception:
            pass
        try:
            self.home_passenger.shutdown()
        except Exception:
            pass

        try:
            if self.current_username:
                self.api_client.disconnect()
            else:
                self.api_client.close()
        except Exception:
            pass

        event.accept()


def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
