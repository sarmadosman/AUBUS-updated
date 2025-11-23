import sys
import requests
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
    QFrame,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class WeatherApp(QMainWindow):
    """
    Simple weather window that shows:
      - current weather conditions
      - 3-day forecast

    Uses WeatherAPI (free tier) as the cloud service,
    satisfying the project requirement that the *client side*
    displays current weather conditions via a cloud service.
    """

    def __init__(self, default_location: str = "Beirut"):
        super().__init__()
        # Replace this with your own API key if needed
        self.api_key = "7a77199e48174a098bf174356251411"
        self.default_location = default_location
        self._build_ui()

        # On startup, automatically show weather for the default location
        # so the client "displays current weather conditions" immediately.
        if self.default_location:
            self.location_input.setText(self.default_location)
            self.get_weather()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        """Initialize the user interface"""
        self.setWindowTitle("3-Day Weather Forecast")
        self.setGeometry(200, 150, 800, 600)
        self.setStyleSheet("background-color: #2C3E50;")

        # Central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)

        # Title
        title = QLabel("Weather Forecast")
        title.setFont(QFont("Arial", 24, QFont.Bold))
        title.setStyleSheet("color: #ECF0F1;")
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # Search section (location + button)
        search_layout = QHBoxLayout()

        self.location_input = QLineEdit()
        self.location_input.setPlaceholderText("Enter city name (e.g., Beirut, London)")
        self.location_input.setFont(QFont("Arial", 12))
        self.location_input.setStyleSheet(
            """
            QLineEdit {
                padding: 10px;
                border: 2px solid #34495E;
                border-radius: 5px;
                background-color: #ECF0F1;
                color: #2C3E50;
            }
        """
        )
        self.location_input.returnPressed.connect(self.get_weather)

        search_btn = QPushButton("Get Weather")
        search_btn.setFont(QFont("Arial", 12, QFont.Bold))
        search_btn.setStyleSheet(
            """
            QPushButton {
                padding: 10px 20px;
                background-color: #3498DB;
                color: white;
                border: none;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #2980B9;
            }
        """
        )
        search_btn.clicked.connect(self.get_weather)

        search_layout.addWidget(self.location_input)
        search_layout.addWidget(search_btn)
        main_layout.addLayout(search_layout)

        # Current weather display (HTML label)
        self.current_weather_label = QLabel("Fetching weather...")
        self.current_weather_label.setFont(QFont("Arial", 14))
        self.current_weather_label.setStyleSheet("color: #ECF0F1; padding: 20px;")
        self.current_weather_label.setAlignment(Qt.AlignCenter)
        self.current_weather_label.setWordWrap(True)
        main_layout.addWidget(self.current_weather_label)

        # 3-day forecast container
        self.forecast_layout = QHBoxLayout()
        self.forecast_layout.setSpacing(15)
        main_layout.addLayout(self.forecast_layout)

        main_layout.addStretch()

    # ------------------------------------------------------------------
    # Weather logic
    # ------------------------------------------------------------------

    def get_weather(self):
        """Fetch weather data from WeatherAPI for the current location input."""
        location = self.location_input.text().strip()

        # If user didn't type anything, fall back to default location (e.g., Beirut)
        if not location:
            if self.default_location:
                location = self.default_location
                self.location_input.setText(location)
            else:
                QMessageBox.warning(self, "Error", "Please enter a location")
                return

        if not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            QMessageBox.warning(self, "Error", "Please set your WeatherAPI key in the code.")
            return

        try:
            url = (
                f"http://api.weatherapi.com/v1/forecast.json"
                f"?key={self.api_key}&q={location}&days=3&aqi=no"
            )
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            self.display_weather(data)

        except requests.exceptions.RequestException as e:
            QMessageBox.critical(self, "Error", f"Failed to fetch weather data:\n{str(e)}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred:\n{str(e)}")

    def display_weather(self, data: dict):
        """Display current weather and 3-day forecast in the UI."""
        # Clear previous forecast cards
        self.clear_forecast()

        # Guard against malformed responses
        if "location" not in data or "current" not in data or "forecast" not in data:
            QMessageBox.warning(self, "Error", "Unexpected response from weather service.")
            return

        location = data["location"]
        current = data["current"]

        # --- Current weather (this is what the project explicitly requires) ---
        current_text = f"""
        <h2>{location.get('name', '')}, {location.get('country', '')}</h2>
        <p style='font-size: 16px;'>
            <b>Temperature:</b> {current.get('temp_c', '?')}°C ({current.get('temp_f', '?')}°F)<br>
            <b>Condition:</b> {current.get('condition', {}).get('text', '')}<br>
            <b>Feels Like:</b> {current.get('feelslike_c', '?')}°C<br>
            <b>Humidity:</b> {current.get('humidity', '?')}%<br>
            <b>Wind:</b> {current.get('wind_kph', '?')} km/h
        </p>
        """
        self.current_weather_label.setText(current_text)

        # --- 3-day forecast cards (bonus, not strictly required but nice) ---
        forecast_days = data.get("forecast", {}).get("forecastday", [])
        for day_data in forecast_days:
            day_widget = self.create_day_forecast(day_data)
            self.forecast_layout.addWidget(day_widget)

    def create_day_forecast(self, day_data: dict) -> QFrame:
        """Create a widget for a single day's forecast."""
        frame = QFrame()
        frame.setStyleSheet(
            """
            QFrame {
                background-color: #34495E;
                border-radius: 10px;
                padding: 15px;
            }
        """
        )

        layout = QVBoxLayout(frame)
        layout.setSpacing(10)

        # Date
        date_label = QLabel(day_data.get("date", ""))
        date_label.setFont(QFont("Arial", 12, QFont.Bold))
        date_label.setStyleSheet("color: #3498DB;")
        date_label.setAlignment(Qt.AlignCenter)

        # Condition text
        condition_text = day_data.get("day", {}).get("condition", {}).get("text", "")
        condition_label = QLabel(condition_text)
        condition_label.setFont(QFont("Arial", 11))
        condition_label.setStyleSheet("color: #ECF0F1;")
        condition_label.setAlignment(Qt.AlignCenter)
        condition_label.setWordWrap(True)

        # Max / min temp
        maxt = day_data.get("day", {}).get("maxtemp_c", "?")
        mint = day_data.get("day", {}).get("mintemp_c", "?")
        temp_label = QLabel(f"Max: {maxt}°C\nMin: {mint}°C")
        temp_label.setFont(QFont("Arial", 11))
        temp_label.setStyleSheet("color: #ECF0F1;")
        temp_label.setAlignment(Qt.AlignCenter)

        # Extra info: chance of rain & humidity
        rain_chance = day_data.get("day", {}).get("daily_chance_of_rain", "?")
        avg_humidity = day_data.get("day", {}).get("avghumidity", "?")
        info_label = QLabel(f"Rain: {rain_chance}%\nHumidity: {avg_humidity}%")
        info_label.setFont(QFont("Arial", 9))
        info_label.setStyleSheet("color: #BDC3C7;")
        info_label.setAlignment(Qt.AlignCenter)

        layout.addWidget(date_label)
        layout.addWidget(condition_label)
        layout.addWidget(temp_label)
        layout.addWidget(info_label)

        return frame

    def clear_forecast(self):
        """Clear previous forecast widgets."""
        while self.forecast_layout.count():
            item = self.forecast_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()


def main():
    app = QApplication(sys.argv)
    # Default location set to Beirut (close to AUB), but user can change it
    window = WeatherApp(default_location="Beirut")
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
