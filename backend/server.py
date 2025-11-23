import socket
import threading
import json
from datetime import datetime

from . import db_api
from .config import SERVER_HOST, SERVER_PORT

# ============================================================
#  Globals
# ============================================================

# Track live users: username → socket
connected_drivers = {}
connected_passengers = {}

# Driver status: username → "available" or "dnd"
driver_status = {}


# ============================================================
#  Utility Helpers
# ============================================================


def safe_send(sock, obj):
    """
    Send JSON safely to a socket, newline-delimited.

    Every message is a single JSON object followed by '\n'.
    """
    try:
        data = json.dumps(obj) + "\n"
        sock.sendall(data.encode("utf-8"))
    except Exception:
        # socket dead/disconnected
        pass


def now_weekday_int():
    """Return current weekday as 0–6."""
    return datetime.now().weekday()


# ============================================================
#  Matching helpers
# ============================================================


def _is_driver_available_online(username: str) -> bool:
    """
    A driver is considered available if:
      - they have a connected socket
      - their status is "available" (not "dnd")
    """
    if username not in connected_drivers:
        return False
    status = driver_status.get(username, "available")
    return status == "available"


def get_matched_available_drivers(
    area: str,
    weekday: int,
    target_seconds: int,
    target_driver: str = None,
    preferred_only: bool = False,
):
    """
    Use DB schedule matching, then filter to drivers who are online + available.

    Normal behaviour (preferred_only=False):
      - If target_driver is provided and they are:
          * in the matched list
          * online + available
        then returns [target_driver] only.
      - Otherwise returns all matched drivers who are online + available.

    Preferred-only behaviour (preferred_only=True and target_driver set):
      - Only returns [target_driver] if they match schedule + are online+available.
      - Otherwise returns [] (no fallback to other drivers).
    """
    matched = db_api.get_available_drivers(area, weekday, target_seconds)

    # Strict mode: only preferred driver, no fallback
    if preferred_only and target_driver:
        if target_driver in matched and _is_driver_available_online(target_driver):
            return [target_driver]
        return []

    # Normal behaviour: prefer target_driver, then others
    if target_driver and target_driver in matched and _is_driver_available_online(
        target_driver
    ):
        return [target_driver]

    # Otherwise all online + available
    return [u for u in matched if _is_driver_available_online(u)]


# ============================================================
#  Notification Helpers
# ============================================================


def notify_matched_drivers(ride_info, target_driver=None, preferred_only: bool = False):
    """
    Notify online + available drivers that match area + time.

    ride_info = {
        ride_id, passenger_username, area, time(seconds), weekday
    }

    Uses the same preferred-driver logic as get_matched_available_drivers.
    Returns True if at least one driver was notified, else False.
    """
    area = ride_info["area"]
    target_sec = ride_info["time"]
    weekday = ride_info["weekday"]

    drivers = get_matched_available_drivers(
        area,
        weekday,
        target_sec,
        target_driver=target_driver,
        preferred_only=preferred_only,
    )

    notified = False
    for username in drivers:
        sock = connected_drivers.get(username)
        if not sock:
            continue
        safe_send(
            sock,
            {
                "action": "new_ride",
                "ride_id": ride_info["ride_id"],
                "passenger_username": ride_info["passenger_username"],
                "area": ride_info["area"],
                "time": ride_info["time"],
                "weekday": ride_info["weekday"],
            },
        )
        notified = True

    return notified


# ============================================================
#  Client Handler
# ============================================================


def handle_client(sock, addr):
    print(f"[NEW CONNECTION] {addr}")
    connected = True
    buffer = ""  # accumulate partial data between recv() calls

    while connected:
        try:
            chunk = sock.recv(4096).decode("utf-8")
            if not chunk:
                break

            buffer += chunk

            # Process all complete JSON lines in the buffer
            while "\n" in buffer:
                raw_line, buffer = buffer.split("\n", 1)
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                data = json.loads(raw_line)
                action = data.get("action")
                username = data.get("username")

                # ====================================================
                #  REGISTER
                # ====================================================
                if action == "register":
                    response = db_api.register_user(data)

                # ====================================================
                #  LOGIN
                # ====================================================
                elif action == "login":
                    response = db_api.login_user(data)
                    if response["status"] == "success":
                        role = response["role"]
                        uname = response["username"]

                        if role == "driver":
                            connected_drivers[uname] = sock
                            # default status = available
                            driver_status[uname] = driver_status.get(uname, "available")
                            print(f"[INFO] Driver connected: {uname}")
                        else:
                            connected_passengers[uname] = sock
                            print(f"[INFO] Passenger connected: {uname}")

                        # Include preferences in the login response
                        prefs = db_api.get_user_preferences(uname)
                        response["preferences"] = prefs

                # ====================================================
                #  PROFILE: GET / UPDATE
                # ====================================================
                elif action == "get_profile":
                    # username comes from data["username"]
                    response = db_api.get_user_profile(data["username"])

                elif action == "update_profile":
                    # data contains username + fields to update
                    response = db_api.update_user_profile(data)

                # ====================================================
                #  CREATE RIDE (Passenger, same-day / current behaviour)
                # ====================================================
                elif action == "create_ride":
                    weekday = data.get("weekday", now_weekday_int())
                    area = data["area"]
                    time_str = data["time"]
                    passenger_username = data["passenger_username"]
                    target_driver = data.get("target_driver_username")
                    preferred_only = bool(data.get("preferred_only", False))

                    # Convert time string once here
                    try:
                        time_sec = db_api.time_to_seconds(time_str)
                    except Exception as e:
                        response = {
                            "status": "error",
                            "message": f"Invalid time format: {e}",
                        }
                        safe_send(sock, response)
                        continue

                    # Check if there are any drivers online + available who match
                    available_drivers = get_matched_available_drivers(
                        area=area,
                        weekday=weekday,
                        target_seconds=time_sec,
                        target_driver=target_driver,
                        preferred_only=preferred_only,
                    )

                    if not available_drivers:
                        # No driver can take this ride right now → do NOT create DB row
                        response = {
                            "status": "error",
                            "message": "No drivers are currently available for that time in your area.",
                        }
                    else:
                        # Create ride request in DB
                        create_res = db_api.create_ride_request(
                            {
                                "passenger_username": passenger_username,
                                "area": area,
                                "time": time_str,
                                "weekday": weekday,
                            }
                        )

                        if create_res["status"] == "success":
                            ride_id = create_res["ride_id"]

                            info = {
                                "ride_id": ride_id,
                                "passenger_username": passenger_username,
                                "area": area,
                                "time": time_sec,
                                "weekday": weekday,
                            }

                            # notify matched (and possibly preferred) drivers
                            threading.Thread(
                                target=notify_matched_drivers,
                                args=(info,),
                                kwargs={
                                    "target_driver": target_driver,
                                    "preferred_only": preferred_only,
                                },
                                daemon=True,
                            ).start()

                        response = create_res

                # ====================================================
                #  PREMIUM: search drivers for future scheduled ride
                # ====================================================
                elif action == "search_scheduled_drivers":
                    area = data.get("area")
                    date_str = data.get("date")
                    time_str = data.get("time")

                    if not area or not date_str or not time_str:
                        response = {
                            "status": "error",
                            "message": "Missing area, date, or time.",
                        }
                    else:
                        try:
                            drivers = db_api.find_drivers_for_datetime(
                                area, date_str, time_str
                            )
                            response = {"status": "success", "drivers": drivers}
                        except Exception as e:
                            response = {"status": "error", "message": str(e)}

                # ====================================================
                #  PREMIUM: create a scheduled ride (future date)
                # ====================================================
                # ====================================================
                #  PREMIUM: create a scheduled ride (future date)
                # ====================================================
                elif action == "create_scheduled_ride":
                    area = data.get("area")
                    date_str = data.get("date")
                    time_str = data.get("time")
                    passenger_username = data.get("passenger_username")
                    driver_username = data.get("driver_username")

                    if not all(
                            [area, date_str, time_str, passenger_username, driver_username]
                    ):
                        response = {
                            "status": "error",
                            "message": "Missing fields for scheduled ride.",
                        }
                    else:
                        try:
                            # Validate that the chosen driver is actually
                            # available according to their weekly_schedule
                            candidates = db_api.find_drivers_for_datetime(
                                area, date_str, time_str
                            )
                            valid_usernames = {d.get("username") for d in candidates}

                            if driver_username not in valid_usernames:
                                response = {
                                    "status": "error",
                                    "message": "Selected driver is not available at that date/time.",
                                }
                            else:
                                create_res = db_api.create_scheduled_ride(
                                    {
                                        "passenger_username": passenger_username,
                                        "driver_username": driver_username,
                                        "area": area,
                                        "date": date_str,
                                        "time": time_str,
                                    }
                                )
                                response = create_res

                                # Notify driver in realtime if connected.
                                if create_res.get("status") == "success":
                                    ride_id = create_res.get("scheduled_ride_id")
                                    dsock = connected_drivers.get(driver_username)
                                    if dsock and ride_id is not None:
                                        safe_send(
                                            dsock,
                                            {
                                                "action": "scheduled_ride_created",
                                                "scheduled_ride_id": ride_id,
                                                "ride": {
                                                    "id": ride_id,
                                                    "passenger_username": passenger_username,
                                                    "driver_username": driver_username,
                                                    "area": area,
                                                    "date": date_str,
                                                    "time": time_str,
                                                },
                                            },
                                        )
                        except Exception as e:
                            response = {"status": "error", "message": str(e)}

                # ====================================================
                #  PREMIUM: get / update scheduled rides
                # ====================================================
                elif action == "get_scheduled_rides":
                    username = data.get("username")
                    role = data.get("role")

                    if not username or role not in ("passenger", "driver"):
                        response = {
                            "status": "error",
                            "message": "Missing username or invalid role.",
                        }
                    else:
                        try:
                            response = db_api.get_scheduled_rides(username, role)
                        except Exception as e:
                            response = {"status": "error", "message": str(e)}

                elif action == "driver_accept_scheduled_ride":
                    ride_id = data.get("ride_id")
                    driver_username = data.get("username")

                    try:
                        ride_id = int(ride_id)
                    except Exception:
                        response = {
                            "status": "error",
                            "message": "Invalid ride_id.",
                        }
                    else:
                        ride = db_api.get_scheduled_ride(ride_id)
                        if not ride:
                            response = {
                                "status": "error",
                                "message": "Scheduled ride not found.",
                            }
                        elif ride.get("driver_username") != driver_username:
                            response = {
                                "status": "error",
                                "message": "You are not the driver for this ride.",
                            }
                        else:
                            ok = db_api.update_scheduled_ride_status(
                                ride_id, "accepted"
                            )
                            if not ok:
                                response = {
                                    "status": "error",
                                    "message": "Could not update scheduled ride.",
                                }
                            else:
                                # notify passenger if online
                                passenger_username = ride.get("passenger_username")
                                psock = connected_passengers.get(passenger_username)
                                if psock:
                                    safe_send(
                                        psock,
                                        {
                                            "action": "scheduled_ride_updated",
                                            "ride_id": ride_id,
                                            "status": "accepted",
                                            "driver_username": driver_username,
                                        },
                                    )

                                response = {
                                    "status": "success",
                                    "message": "Scheduled ride accepted.",
                                }

                elif action == "driver_decline_scheduled_ride":
                    ride_id = data.get("ride_id")
                    driver_username = data.get("username")

                    try:
                        ride_id = int(ride_id)
                    except Exception:
                        response = {
                            "status": "error",
                            "message": "Invalid ride_id.",
                        }
                    else:
                        ride = db_api.get_scheduled_ride(ride_id)
                        if not ride:
                            response = {
                                "status": "error",
                                "message": "Scheduled ride not found.",
                            }
                        elif ride.get("driver_username") != driver_username:
                            response = {
                                "status": "error",
                                "message": "You are not the driver for this ride.",
                            }
                        else:
                            ok = db_api.update_scheduled_ride_status(
                                ride_id, "declined"
                            )
                            if not ok:
                                response = {
                                    "status": "error",
                                    "message": "Could not update scheduled ride.",
                                }
                            else:
                                # notify passenger if online
                                passenger_username = ride.get("passenger_username")
                                psock = connected_passengers.get(passenger_username)
                                if psock:
                                    safe_send(
                                        psock,
                                        {
                                            "action": "scheduled_ride_updated",
                                            "ride_id": ride_id,
                                            "status": "declined",
                                            "driver_username": driver_username,
                                        },
                                    )

                                response = {
                                    "status": "success",
                                    "message": "Scheduled ride declined.",
                                }

                elif action == "passenger_cancel_scheduled_ride":
                    ride_id = data.get("ride_id")
                    passenger_username = data.get("username")

                    try:
                        ride_id = int(ride_id)
                    except Exception:
                        response = {
                            "status": "error",
                            "message": "Invalid ride_id.",
                        }
                    else:
                        ride = db_api.get_scheduled_ride(ride_id)
                        if not ride:
                            response = {
                                "status": "error",
                                "message": "Scheduled ride not found.",
                            }
                        elif ride.get("passenger_username") != passenger_username:
                            response = {
                                "status": "error",
                                "message": "You are not the passenger for this ride.",
                            }
                        else:
                            ok = db_api.update_scheduled_ride_status(
                                ride_id, "canceled"
                            )
                            if not ok:
                                response = {
                                    "status": "error",
                                    "message": "Could not update scheduled ride.",
                                }
                            else:
                                # notify driver if online
                                driver_username = ride.get("driver_username")
                                dsock = connected_drivers.get(driver_username)
                                if dsock:
                                    safe_send(
                                        dsock,
                                        {
                                            "action": "scheduled_ride_updated",
                                            "ride_id": ride_id,
                                            "status": "canceled",
                                            "passenger_username": passenger_username,
                                        },
                                    )

                                response = {
                                    "status": "success",
                                    "message": "Scheduled ride canceled.",
                                }

                # ====================================================
                #  DRIVER ACCEPTS RIDE (immediate)
                # ====================================================
                elif action == "accept_ride":
                    ride_id = data["ride_id"]
                    driver_username = data["username"]
                    driver_ip = data.get("driver_ip")
                    driver_port = data.get("driver_port")

                    if db_api.accept_ride(ride_id, driver_username, driver_ip, driver_port):

                        # Retrieve passenger username to notify them
                        ride_history = db_api.get_ride_history(driver_username, "driver")
                        passenger_username = None
                        for r in ride_history["rides"]:
                            if r["id"] == ride_id:
                                passenger_username = r["passenger_username"]
                                break

                        if passenger_username:
                            psock = connected_passengers.get(passenger_username)
                            if psock:
                                safe_send(
                                    psock,
                                    {
                                        "action": "ride_accepted",
                                        "ride_id": ride_id,
                                        "driver_username": driver_username,
                                        "driver_ip": driver_ip,
                                        "driver_port": driver_port,
                                    },
                                )

                        response = {"status": "success", "message": "Ride accepted."}

                    else:
                        response = {
                            "status": "error",
                            "message": "Ride already taken or invalid.",
                        }

                # ====================================================
                #  GET PENDING RIDES (Driver)
                # ====================================================
                elif action == "get_pending_rides":
                    area = data["area"]
                    response = {
                        "status": "success",
                        "rides": db_api.get_pending_rides(area),
                    }

                # ====================================================
                #  COMPLETE RIDE
                # ====================================================
                elif action == "complete_ride":
                    ride_id = data["ride_id"]
                    driver_username = data["username"]

                    ok = db_api.complete_ride(ride_id, driver_username)
                    if ok:
                        response = {
                            "status": "success",
                            "message": "Ride completed.",
                        }

                        # Also notify the passenger so they can close chat and rate the driver
                        try:
                            ride_info = db_api.get_ride_by_id(ride_id)
                        except Exception:
                            ride_info = None

                        if ride_info:
                            passenger_username = ride_info.get("passenger_username")
                            driver_username = ride_info.get("driver_username")
                            psock = connected_passengers.get(passenger_username)
                            if psock:
                                try:
                                    safe_send(
                                        psock,
                                        {
                                            "action": "ride_completed",
                                            "ride_id": ride_id,
                                            "passenger_username": passenger_username,
                                            "driver_username": driver_username,
                                        },
                                    )
                                except Exception as e:
                                    print(
                                        f"[WARN] Failed to send ride_completed to passenger: {e}"
                                    )
                    else:
                        response = {
                            "status": "error",
                            "message": "Ride not found or cannot be completed.",
                        }

                # ====================================================
                #  SUBMIT RATING
                # ====================================================
                elif action == "submit_rating":
                    response = db_api.submit_rating(data)

                # ====================================================
                #  GET AVERAGE RATING
                # ====================================================
                elif action == "get_rating":
                    avg = db_api.get_average_rating(data["username"])
                    response = {"status": "success", "rating": avg}

                # ====================================================
                #  RIDE HISTORY
                # ====================================================
                elif action == "get_ride_history":
                    response = db_api.get_ride_history(
                        data["username"], data["role"]
                    )

                # ====================================================
                #  LIST DRIVERS (premium)
                # ====================================================
                elif action == "list_drivers":
                    area = data.get("area")
                    response = db_api.list_drivers(area)
                    # enrich with online + status
                    drivers = response.get("drivers", [])
                    for d in drivers:
                        uname = d.get("username")
                        online = uname in connected_drivers
                        d["online"] = online
                        if online:
                            d["status"] = driver_status.get(uname, "available")
                        else:
                            d["status"] = "offline"

                # ====================================================
                #  SET DRIVER STATUS (available / dnd)
                # ====================================================
                elif action == "set_status":
                    # only meaningful for drivers
                    uname = data.get("username")
                    status_value = data.get("status", "available")
                    if uname and uname in connected_drivers:
                        if status_value not in ("available", "dnd"):
                            status_value = "available"
                        driver_status[uname] = status_value
                        response = {"status": "success", "status_value": status_value}
                    else:
                        response = {
                            "status": "error",
                            "message": "Driver not connected or username missing.",
                        }

                # ====================================================
                #  GET / SAVE USER PREFERENCES
                # ====================================================
                elif action == "get_preferences":
                    response = {
                        "status": "success",
                        "preferences": db_api.get_user_preferences(data["username"]),
                    }

                elif action == "save_preferences":
                    db_api.save_user_preferences(
                        data["username"], data["preferences"]
                    )
                    response = {"status": "success"}

                # ====================================================
                #  DISCONNECT
                # ====================================================
                elif action == "disconnect":
                    connected = False
                    response = {"status": "success", "message": "Disconnected."}

                    uname = data.get("username")
                    if uname:
                        connected_drivers.pop(uname, None)
                        connected_passengers.pop(uname, None)
                        driver_status.pop(uname, None)

                # ====================================================
                #  DECLINE RIDE
                # ====================================================
                elif action == "decline_ride":
                    ride_id = data.get("ride_id")
                    driver_username = data.get("username")
                    if ride_id is None:
                        response = {
                            "status": "error",
                            "message": "Missing ride_id",
                        }
                    else:
                        ok = db_api.decline_ride(ride_id)
                        if ok:
                            # Notify passenger that their request was declined
                            ride_info = db_api.get_ride_by_id(ride_id)
                            if ride_info:
                                passenger_username = ride_info.get(
                                    "passenger_username"
                                )
                                psock = connected_passengers.get(passenger_username)
                                if psock:
                                    safe_send(
                                        psock,
                                        {
                                            "action": "ride_declined",
                                            "ride_id": ride_id,
                                            "driver_username": driver_username,
                                        },
                                    )

                            response = {
                                "status": "success",
                                "message": "Ride declined.",
                            }
                        else:
                            response = {
                                "status": "error",
                                "message": "Ride not found or not pending.",
                            }

                # ====================================================
                #  UNKNOWN ACTION
                # ====================================================
                else:
                    response = {
                        "status": "error",
                        "message": "Unknown action.",
                    }

                # Send back the response for this one message
                safe_send(sock, response)

        except Exception as e:
            print(f"[ERROR] {addr}: {e}")
            break

    sock.close()
    print(f"[DISCONNECTED] {addr}")


# ============================================================
#  Server Start
# ============================================================


def start_server(host=SERVER_HOST, port=SERVER_PORT):
    print(
        "[DEBUG] Server datetime now =",
        datetime.now(),
        "weekday=",
        datetime.now().weekday(),
    )

    db_api.init_db()  # ensure schema exists

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind((host, port))
    srv.listen(20)

    print(f"[STARTED] Server running on {host}:{port}")

    while True:
        client_sock, addr = srv.accept()
        t = threading.Thread(
            target=handle_client, args=(client_sock, addr), daemon=True
        )
        t.start()


# ============================================================
#  Run directly
# ============================================================

if __name__ == "__main__":
    print("[INFO] Starting AUBus server...")
    start_server()
