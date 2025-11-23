import os

# Base directory for the whole project (aubus/)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Path to the SQLite DB file
DB_PATH = os.path.join(BASE_DIR, "aubus.db")

# TCP JSON server settings
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 5555

# Default port for P2P chat (driver side)
DEFAULT_P2P_PORT = 6000

# Time window (in minutes) for matching drivers near requested time
DRIVER_TIME_MATCH_WINDOW_MIN = 10

# Optional: Weather API key if you want to centralize it
WEATHER_API_KEY = "7a77199e48174a098bf174356251411"  # or override via env
