import json
import socket
from typing import Any, Dict, Optional, Callable
import threading

DEFAULT_SERVER_HOST = "127.0.0.1"
DEFAULT_SERVER_PORT = 5555

DEFAULT_TIMEOUT = 5.0
BUFFER_SIZE = 4096
MSG_DELIM = b"\n"

# Core helper: send a single JSON request and receive a JSON response
def send_request(
    payload: Dict[str, Any],
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    try:
        data_out = (json.dumps(payload) + "\n").encode("utf-8")
    except Exception as e:
        return {"status": "error", "message": f"Failed to encode request JSON: {e}"}

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        sock.sendall(data_out)

        buffer = b""
        line: Optional[bytes] = None

        while True:
            chunk = sock.recv(BUFFER_SIZE)
            if not chunk:
                break
            buffer += chunk
            if MSG_DELIM in buffer:
                line, _ = buffer.split(MSG_DELIM, 1)
                break

        sock.close()

        if not buffer or line is None:
            return {"status": "error", "message": "Empty or incomplete response from server"}

        try:
            response = json.loads(line.decode("utf-8"))
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to decode server JSON: {e}; raw={buffer!r}",
            }

        return response

    except socket.timeout:
        return {"status": "error", "message": "Connection to server timed out"}
    except ConnectionRefusedError:
        return {
            "status": "error",
            "message": "Connection refused – is the AUBus server running?",
        }
    except OSError as e:
        return {
            "status": "error",
            "message": f"Socket error: {e}",
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Unexpected error in send_request: {e}",
        }



# Helpers (register/login/rides/ratings/preferences/profile)
def register_user(
    username: str,
    password: str,
    area: str,
    role: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    weekly_schedule: Optional[dict] = None,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    if name is None:
        name = username
    if email is None:
        email = f"{username}@example.com"

    payload: Dict[str, Any] = {
        "action": "register",
        "username": username,
        "password": password,
        "name": name,
        "email": email,
        "area": area,
        "role": role,
    }

    if weekly_schedule is not None:
        payload["weekly_schedule"] = weekly_schedule

    return send_request(payload, host=host, port=port)


def login_user(
    username: str,
    password: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "login",
        "username": username,
        "password": password,
    }
    return send_request(payload, host=host, port=port)


def disconnect(
    username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "disconnect",
        "username": username,
    }
    return send_request(payload, host=host, port=port)

#PREMIUM: PREFERRED/ONLY PREFERRED DRIVERS (NOT RANDOM MATCHING)
def create_ride(
    passenger_username: str,
    area: str,
    time_str: str,
    target_driver_username: Optional[str] = None,
    preferred_only: bool = False,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    """
    Create a ride request for today at time_str.
    If target_driver_username is given:
      - preferred_only=False (default): try preferred driver first, then fall back.
      - preferred_only=True: only match to that driver; if not available, fail.
    """
    payload: Dict[str, Any] = {
        "action": "create_ride",
        "passenger_username": passenger_username,
        "area": area,
        "time": time_str,
    }
    if target_driver_username:
        payload["target_driver_username"] = target_driver_username
    if preferred_only:
        payload["preferred_only"] = True

    return send_request(payload, host=host, port=port)

client_create_ride = create_ride

def get_pending_rides(
    area: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "get_pending_rides",
        "area": area,
    }
    return send_request(payload, host=host, port=port)

client_get_pending_rides = get_pending_rides

def accept_ride(
    ride_id: int,
    driver_username: str,
    driver_ip: str,
    driver_port: int,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "accept_ride",
        "ride_id": ride_id,
        "username": driver_username,
        "driver_ip": driver_ip,
        "driver_port": driver_port,
    }
    return send_request(payload, host=host, port=port)

client_accept_ride = accept_ride

def complete_ride(
    ride_id: int,
    driver_username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "complete_ride",
        "ride_id": ride_id,
        "username": driver_username,
    }
    return send_request(payload, host=host, port=port)


def decline_ride(
    ride_id: int,
    driver_username: Optional[str] = None,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "decline_ride",
        "ride_id": ride_id,
    }
    if driver_username is not None:
        payload["username"] = driver_username
    return send_request(payload, host=host, port=port)


def get_ride_history(
    username: str,
    role: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "get_ride_history",
        "username": username,
        "role": role,
    }
    return send_request(payload, host=host, port=port)


def submit_rating(
    ride_id: int,
    rater_username: str,
    ratee_username: str,
    score: int,
    comment: str = "",
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "submit_rating",
        "ride_id": ride_id,
        "rater_username": rater_username,
        "ratee_username": ratee_username,
        "score": score,
        "comment": comment,
    }
    return send_request(payload, host=host, port=port)


def get_rating(
    username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "get_rating",
        "username": username,
    }
    return send_request(payload, host=host, port=port)


def get_preferences(
    username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "get_preferences",
        "username": username,
    }
    return send_request(payload, host=host, port=port)


def save_preferences(
    username: str,
    preferences: Dict[str, Any],
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "save_preferences",
        "username": username,
        "preferences": preferences,
    }
    return send_request(payload, host=host, port=port)


def list_drivers(
    area: str = None,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    """
    Get a list of drivers, optionally filtered by area.
    """
    payload: Dict[str, Any] = {
        "action": "list_drivers",
    }
    if area:
        payload["area"] = area
    return send_request(payload, host=host, port=port)

client_list_drivers = list_drivers


#PROFILE
def get_profile(
    username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "get_profile",
        "username": username,
    }
    return send_request(payload, host=host, port=port)


def update_profile(
    username: str,
    name: Optional[str],
    email: Optional[str],
    area: Optional[str],
    password: Optional[str] = None,
    weekly_schedule: Optional[dict] = None,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "action": "update_profile",
        "username": username,
    }
    if name is not None:
        payload["name"] = name
    if email is not None:
        payload["email"] = email
    if area is not None:
        payload["area"] = area
    if password:
        payload["password"] = password
    if weekly_schedule is not None:
        payload["weekly_schedule"] = weekly_schedule
    return send_request(payload, host=host, port=port)


#PREMIUM: SCHEDULED RIDES
def create_scheduled_ride(
    passenger_username: str,
    driver_username: str,
    area: str,
    date_str: str,
    time_str: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    """
    Schedule a future ride with a specific driver.
    date_str: "YYYY-MM-DD"
    time_str: "HH:MM"
    """
    payload: Dict[str, Any] = {
        "action": "create_scheduled_ride",
        "passenger_username": passenger_username,
        "driver_username": driver_username,
        "area": area,
        "date": date_str,
        "date_str": date_str,
        "time": time_str,
        "time_str": time_str,
    }
    return send_request(payload, host=host, port=port)


def get_scheduled_rides(
    username: str,
    role: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "get_scheduled_rides",
        "username": username,
        "role": role,
    }
    return send_request(payload, host=host, port=port)


def driver_accept_scheduled_ride(
    ride_id: int,
    driver_username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "driver_accept_scheduled_ride",
        "ride_id": ride_id,
        "username": driver_username,
    }
    return send_request(payload, host=host, port=port)


def driver_decline_scheduled_ride(
    ride_id: int,
    driver_username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "driver_decline_scheduled_ride",
        "ride_id": ride_id,
        "username": driver_username,
    }
    return send_request(payload, host=host, port=port)


def passenger_cancel_scheduled_ride(
    ride_id: int,
    passenger_username: str,
    host: str = DEFAULT_SERVER_HOST,
    port: int = DEFAULT_SERVER_PORT,
) -> Dict[str, Any]:
    payload = {
        "action": "passenger_cancel_scheduled_ride",
        "ride_id": ride_id,
        "username": passenger_username,
    }
    return send_request(payload, host=host, port=port)


class RealtimeClient:
    """
    Realtime AUBus client with a persistent TCP connection and a listener
    thread for server push notifications. Messages are JSON objects.
    """
    def __init__(
        self,
        host: str = DEFAULT_SERVER_HOST,
        port: int = DEFAULT_SERVER_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

        self._sock: Optional[socket.socket] = None
        self._listener_thread: Optional[threading.Thread] = None
        self._running = False

        # For synchronous request/response
        self._send_lock = threading.Lock()
        self._response_event = threading.Event()
        self._pending_response: Optional[Dict[str, Any]] = None

        # Session info
        self.username: Optional[str] = None
        self.role: Optional[str] = None
        self.area: Optional[str] = None
        self.preferences: Optional[Dict[str, Any]] = None

        # Notification callbacks
        self.on_new_ride: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_ride_accepted: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_ride_declined: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_ride_completed: Optional[Callable[[Dict[str, Any]], None]] = None
        self.on_other_notification: Optional[Callable[[Dict[str, Any]], None]] = None

    #CONNECTION MANAGEMENT
    def _ensure_connected(self) -> None:
        if self._sock is not None:
            return
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(None)  # blocking; listener thread handles recv
        s.connect((self.host, self.port))
        self._sock = s
        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listener_loop, daemon=True
        )
        self._listener_thread.start()

    def close(self) -> None:
        self._running = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None

    #SEND/RECEIVE
    def _send_and_wait(
        self, payload: Dict[str, Any], timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        self._ensure_connected()

        try:
            data_out = (json.dumps(payload) + "\n").encode("utf-8")
        except Exception as e:
            return {"status": "error", "message": f"Failed to encode JSON: {e}"}

        with self._send_lock:
            self._response_event.clear()
            self._pending_response = None

            try:
                assert self._sock is not None
                self._sock.sendall(data_out)
            except Exception as e:
                return {"status": "error", "message": f"Socket send error: {e}"}

        wait_timeout = timeout if timeout is not None else self.timeout
        if not self._response_event.wait(wait_timeout):
            return {"status": "error", "message": "Timed out waiting for server response"}

        return self._pending_response or {
            "status": "error",
            "message": "No response from server",
        }

    def _listener_loop(self) -> None:
        buffer = b""

        while self._running and self._sock is not None:
            try:
                data = self._sock.recv(BUFFER_SIZE)
                if not data:
                    break

                buffer += data

                # Process all complete lines in the buffer
                while MSG_DELIM in buffer:
                    line, buffer = buffer.split(MSG_DELIM, 1)
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except Exception as e:
                        print(
                            f"[RealtimeClient] JSON decode error: {e}, raw={line!r}"
                        )
                        continue

                    if isinstance(msg, dict) and ("status" in msg) and ("action" not in msg):
                        self._pending_response = msg
                        self._response_event.set()
                    else:
                        self._handle_notification(msg)

            except OSError as e:
                print(f"[RealtimeClient] Socket error in listener: {e}")
                break
            except Exception as e:
                print(f"[RealtimeClient] Unexpected error in listener: {e}")
                break

        self._running = False
        try:
            if self._sock:
                self._sock.close()
        except Exception:
            pass
        self._sock = None
        print("[RealtimeClient] Listener stopped.")

    def _handle_notification(self, msg: Dict[str, Any]) -> None:
        action = msg.get("action")
        if action == "new_ride":
            if self.on_new_ride:
                self.on_new_ride(msg)
        elif action == "ride_accepted":
            if self.on_ride_accepted:
                self.on_ride_accepted(msg)
        elif action == "ride_declined":
            if self.on_ride_declined:
                self.on_ride_declined(msg)
        elif action == "ride_completed":
            if self.on_ride_completed:
                self.on_ride_completed(msg)
        else:
            if self.on_other_notification:
                self.on_other_notification(msg)
            else:
                print("[RealtimeClient] Notification:", msg)

    #API
    def connect_and_login(self, username: str, password: str) -> Dict[str, Any]:
        self._ensure_connected()
        return self.login(username, password)

    def login(self, username: str, password: str) -> Dict[str, Any]:
        payload = {
            "action": "login",
            "username": username,
            "password": password,
        }
        resp = self._send_and_wait(payload)
        if resp.get("status") == "success":
            self.username = resp.get("username", username)
            self.role = resp.get("role")
            self.area = resp.get("area")
            self.preferences = resp.get("preferences")
        return resp

    def register_user(
        self,
        username: str,
        password: str,
        area: str,
        role: str,
        name: Optional[str] = None,
        email: Optional[str] = None,
        weekly_schedule: Optional[dict] = None,
    ) -> Dict[str, Any]:
        if name is None:
            name = username
        if email is None:
            email = f"{username}@example.com"

        payload: Dict[str, Any] = {
            "action": "register",
            "username": username,
            "password": password,
            "name": name,
            "email": email,
            "area": area,
            "role": role,
        }
        if weekly_schedule is not None:
            payload["weekly_schedule"] = weekly_schedule

        return self._send_and_wait(payload)

    def create_ride(
        self,
        passenger_username: str,
        area: str,
        time_str: str,
        target_driver_username: Optional[str] = None,
        preferred_only: bool = False,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "action": "create_ride",
            "passenger_username": passenger_username,
            "area": area,
            "time": time_str,
        }
        if target_driver_username:
            payload["target_driver_username"] = target_driver_username
        if preferred_only:
            payload["preferred_only"] = True
        return self._send_and_wait(payload)

    def get_pending_rides(self, area: Optional[str] = None) -> Dict[str, Any]:
        if area is None:
            area = self.area or ""
        payload = {
            "action": "get_pending_rides",
            "area": area,
        }
        return self._send_and_wait(payload)

    def accept_ride(
        self,
        ride_id: int,
        driver_username: Optional[str] = None,
        driver_ip: str = "127.0.0.1",
        driver_port: int = 6000,
    ) -> Dict[str, Any]:
        if driver_username is None:
            driver_username = self.username or ""
        payload = {
            "action": "accept_ride",
            "ride_id": ride_id,
            "username": driver_username,
            "driver_ip": driver_ip,
            "driver_port": driver_port,
        }
        return self._send_and_wait(payload)

    def decline_ride(self, ride_id: int) -> Dict[str, Any]:
        payload = {
            "action": "decline_ride",
            "ride_id": ride_id,
        }
        if self.username:
            payload["username"] = self.username
        return self._send_and_wait(payload)

    def complete_ride(
        self, ride_id: int, driver_username: Optional[str] = None
    ) -> Dict[str, Any]:
        if driver_username is None:
            driver_username = self.username or ""
        payload = {
            "action": "complete_ride",
            "ride_id": ride_id,
            "username": driver_username,
        }
        return self._send_and_wait(payload)

    def get_ride_history(
        self, username: Optional[str] = None, role: Optional[str] = None
    ) -> Dict[str, Any]:
        if username is None:
            username = self.username or ""
        if role is None:
            role = self.role or ""
        payload = {
            "action": "get_ride_history",
            "username": username,
            "role": role,
        }
        return self._send_and_wait(payload)

    def submit_rating(
        self,
        ride_id: int,
        rater_username: Optional[str],
        ratee_username: str,
        score: int,
        comment: str = "",
    ) -> Dict[str, Any]:
        if rater_username is None:
            rater_username = self.username or ""
        payload = {
            "action": "submit_rating",
            "ride_id": ride_id,
            "rater_username": rater_username,
            "ratee_username": ratee_username,
            "score": score,
            "comment": comment,
        }
        return self._send_and_wait(payload)

    def get_rating(self, username: Optional[str] = None) -> Dict[str, Any]:
        if username is None:
            username = self.username or ""
        payload = {
            "action": "get_rating",
            "username": username,
        }
        return self._send_and_wait(payload)

    def get_preferences(self, username: Optional[str] = None) -> Dict[str, Any]:
        if username is None:
            username = self.username or ""
        payload = {
            "action": "get_preferences",
            "username": username,
        }
        return self._send_and_wait(payload)

    def save_preferences(
        self, username: Optional[str], preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        if username is None:
            username = self.username or ""
        payload = {
            "action": "save_preferences",
            "username": username,
            "preferences": preferences,
        }
        resp = self._send_and_wait(payload)
        if resp.get("status") == "success":
            # keep local copy in sync
            self.preferences = dict(preferences)
        return resp

    def list_drivers(self, area: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"action": "list_drivers"}
        if area:
            payload["area"] = area
        return self._send_and_wait(payload)

    def set_status(self, status: str) -> Dict[str, Any]:
        """
        Driver status: "available" or "dnd".
        """
        if not self.username:
            return {"status": "error", "message": "Not logged in"}
        if status not in ("available", "dnd"):
            status = "available"
        payload = {
            "action": "set_status",
            "username": self.username,
            "status": status,
        }
        return self._send_and_wait(payload)

    def disconnect(self) -> Dict[str, Any]:
        if not self.username:
            self.close()
            return {"status": "success", "message": "Disconnected."}

        payload = {
            "action": "disconnect",
            "username": self.username,
        }
        resp = self._send_and_wait(payload)
        self.close()
        return resp

    #PROFILE
    def get_profile(self, username: Optional[str] = None) -> Dict[str, Any]:
        if username is None:
            username = self.username or ""
        payload = {
            "action": "get_profile",
            "username": username,
        }
        return self._send_and_wait(payload)

    def update_profile(
        self,
        name: Optional[str],
        email: Optional[str],
        area: Optional[str],
        password: Optional[str] = None,
        weekly_schedule: Optional[dict] = None,
    ) -> Dict[str, Any]:
        if not self.username:
            return {"status": "error", "message": "Not logged in"}

        payload: Dict[str, Any] = {
            "action": "update_profile",
            "username": self.username,
        }
        if name is not None:
            payload["name"] = name
        if email is not None:
            payload["email"] = email
        if area is not None:
            payload["area"] = area
        if password:
            payload["password"] = password
        if weekly_schedule is not None:
            payload["weekly_schedule"] = weekly_schedule

        resp = self._send_and_wait(payload)
        # keep local area in sync if updated
        if resp.get("status") == "success" and area is not None:
            self.area = area
        return resp

    #PREMIUM: SCHEDULED RIDES
    def create_scheduled_ride(
        self,
        passenger_username: str,
        driver_username: str,
        area: str,
        date_str: str,
        time_str: str,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "action": "create_scheduled_ride",
            "passenger_username": passenger_username,
            "driver_username": driver_username,
            "area": area,
            "date": date_str,
            "date_str": date_str,
            "time": time_str,
            "time_str": time_str,
        }
        return self._send_and_wait(payload)

    def get_scheduled_rides(
        self,
        username: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        if username is None:
            username = self.username or ""
        if role is None:
            role = self.role or ""
        payload = {
            "action": "get_scheduled_rides",
            "username": username,
            "role": role,
        }
        return self._send_and_wait(payload)

    def driver_accept_scheduled_ride(self, ride_id: int) -> Dict[str, Any]:
        if not self.username:
            return {"status": "error", "message": "Not logged in"}
        payload = {
            "action": "driver_accept_scheduled_ride",
            "ride_id": ride_id,
            "username": self.username,
        }
        return self._send_and_wait(payload)

    def driver_decline_scheduled_ride(self, ride_id: int) -> Dict[str, Any]:
        if not self.username:
            return {"status": "error", "message": "Not logged in"}
        payload = {
            "action": "driver_decline_scheduled_ride",
            "ride_id": ride_id,
            "username": self.username,
        }
        return self._send_and_wait(payload)

    def passenger_cancel_scheduled_ride(self, ride_id: int) -> Dict[str, Any]:
        if not self.username:
            return {"status": "error", "message": "Not logged in"}
        payload = {
            "action": "passenger_cancel_scheduled_ride",
            "ride_id": ride_id,
            "username": self.username,
        }
        return self._send_and_wait(payload)
