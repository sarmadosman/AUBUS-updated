import sqlite3
import json
from datetime import datetime
from pathlib import Path
from .config import DB_PATH

# Helper functions
def time_to_seconds(time_str):
    """Converts 'HH:MM' or 'HH:MM:SS' or '8:30AM' into seconds from midnight."""
    from datetime import datetime
    formats = ['%H:%M', '%H:%M:%S', '%I:%M %p', '%I:%M%p']
    last_err = None

    for fmt in formats:
        try:
            t = datetime.strptime(time_str.strip(), fmt).time()
            return t.hour * 3600 + t.minute * 60 + t.second
        except Exception as e:
            last_err = e

    try:
        s = time_str.strip()
        if s.lower().endswith(("am", "pm")) and not s.lower().endswith((" am", " pm")):
            s = s[:-2] + " " + s[-2:]
            t = datetime.strptime(s, "%I:%M %p").time()
            return t.hour * 3600 + t.minute * 60 + t.second
    except:
        pass

    # Accept raw integer seconds
    try:
        return int(time_str)
    except:
        raise ValueError(f"Unrecognized time format: '{time_str}'")


def weekday_to_int(name):
    """Convert weekday name to integer 0–6."""
    mapping = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    return mapping[name.lower()]


def ensure_json(obj):
    return json.dumps(obj) if not isinstance(obj, str) else obj



# DB Initialization
def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_conn()
    c = conn.cursor()

    # USERS
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            area TEXT NOT NULL,
            role TEXT NOT NULL,
            weekly_schedule TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # SAME-DAY RIDES
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS rides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passenger_username TEXT NOT NULL,
            area TEXT NOT NULL,
            time INTEGER NOT NULL,
            weekday INTEGER NOT NULL,
            status TEXT DEFAULT 'pending',
            driver_username TEXT,
            driver_ip TEXT,
            driver_port INTEGER
        )
    """
    )

    # RATINGS
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS ratings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ride_id INTEGER NOT NULL,
            rater_username TEXT NOT NULL,
            ratee_username TEXT NOT NULL,
            score INTEGER NOT NULL,
            comment TEXT
        )
    """
    )

    # USER PREFERENCES
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            sidebar_color TEXT DEFAULT '#2c3e50',
            background_color TEXT DEFAULT '#FFEAEC',
            button_color TEXT DEFAULT '#2c3e50',
            button_hover_color TEXT DEFAULT '#34495e',
            text_color TEXT DEFAULT 'white',
            theme_name TEXT DEFAULT 'default',
            font_size INTEGER DEFAULT 14
        )
    """
    )

    # ensures preferred_driver_username column exists
    c.execute("PRAGMA table_info(user_preferences)")
    cols = [row[1] for row in c.fetchall()]
    if "preferred_driver_username" not in cols:
        c.execute(
            "ALTER TABLE user_preferences ADD COLUMN preferred_driver_username TEXT"
        )

    # [PREMIUM] SCHEDULED-RIDES
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_rides (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            passenger_username TEXT NOT NULL,
            driver_username TEXT NOT NULL,
            area TEXT NOT NULL,
            date TEXT NOT NULL,        -- ISO date YYYY-MM-DD
            time INTEGER NOT NULL,     -- seconds from midnight
            weekday INTEGER NOT NULL,  -- 0=Mon .. 6=Sun
            status TEXT DEFAULT 'scheduled',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()



# USER MANAGEMENT
def register_user(data):
    """
    data = {
        name, email, username, password, area, role,
        weekly_schedule: dict(day -> "HH:MM")
    }
    """

    conn = get_conn()
    c = conn.cursor()

    try:
        schedule_json = ensure_json(data.get("weekly_schedule", {}))

        c.execute(
            """
            INSERT INTO users (name, email, username, password, area, role, weekly_schedule)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                data["name"],
                data["email"],
                data["username"],
                data["password"],
                data["area"],
                data["role"],
                schedule_json,
            ),
        )

        conn.commit()
        return {"status": "success", "message": "User registered successfully"}

    except sqlite3.IntegrityError:
        return {"status": "error", "message": "Username already exists"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        conn.close()


def login_user(data):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT name, email, username, password, area, role, weekly_schedule 
        FROM users WHERE username=? AND password=?
    """,
        (data["username"], data["password"]),
    )

    user = c.fetchone()
    conn.close()

    if not user:
        return {"status": "error", "message": "Invalid username or password"}

    return {
        "status": "success",
        "message": "Login successful",
        "name": user[0],
        "email": user[1],
        "username": user[2],
        "area": user[4],
        "role": user[5],
        "weekly_schedule": json.loads(user[6]) if user[6] else {},
    }


# fetch basic profile info for a user
def get_user_profile(username: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT name, email, username, area, role, weekly_schedule
        FROM users
        WHERE username=?
        """,
        (username,),
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return {"status": "error", "message": "User not found"}

    name, email, uname, area, role, weekly_schedule = row
    try:
        schedule = json.loads(weekly_schedule) if weekly_schedule else {}
    except Exception:
        schedule = {}

    return {
        "status": "success",
        "name": name,
        "email": email,
        "username": uname,
        "area": area,
        "role": role,
        "weekly_schedule": schedule,
    }


# update basic profile info (name, email, area, password, schedule)
def update_user_profile(data: dict):
    """
    data should contain:
      - username (required, identifies row)
      - name (optional)
      - email (optional)
      - area (optional)
      - password (optional, new password)
      - weekly_schedule (optional dict/JSON string)

    We do NOT change username or role here.
    """
    username = data.get("username")
    if not username:
        return {"status": "error", "message": "Missing username"}

    fields = []
    params = []

    if "name" in data and data["name"] is not None:
        fields.append("name=?")
        params.append(data["name"])

    if "email" in data and data["email"] is not None:
        fields.append("email=?")
        params.append(data["email"])

    if "area" in data and data["area"] is not None:
        fields.append("area=?")
        params.append(data["area"])

    if "password" in data and data["password"] is not None:
        fields.append("password=?")
        params.append(data["password"])

    if "weekly_schedule" in data and data["weekly_schedule"] is not None:
        schedule_json = ensure_json(data["weekly_schedule"])
        fields.append("weekly_schedule=?")
        params.append(schedule_json)

    if not fields:
        return {"status": "error", "message": "No profile fields to update"}

    params.append(username)

    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            f"""
            UPDATE users
            SET {", ".join(fields)}
            WHERE username=?
            """,
            tuple(params),
        )
        conn.commit()
        if c.rowcount == 0:
            return {"status": "error", "message": "User not found"}
        return {"status": "success", "message": "Profile updated"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()



# USER PREFERENCES
def get_user_preferences(username):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT sidebar_color, background_color, button_color,
               button_hover_color, text_color, theme_name, font_size,
               preferred_driver_username
        FROM user_preferences WHERE username=?
    """,
        (username,),
    )

    row = c.fetchone()
    conn.close()

    if row:
        theme_name = row[5] or "default"
        prefs = {
            "sidebar_color": row[0],
            "background_color": row[1],
            "button_color": row[2],
            "button_hover_color": row[3],
            "text_color": row[4],
            "theme_name": theme_name,
            "font_size": row[6],
            "preferred_driver_username": row[7],
        }
        # External API: also expose "theme" key for convenience
        prefs["theme"] = theme_name
        return prefs

    # create new defaults
    defaults = {
        "sidebar_color": "#2c3e50",
        "background_color": "#FFEAEC",
        "button_color": "#2c3e50",
        "button_hover_color": "#34495e",
        "text_color": "white",
        "theme_name": "default",
        "font_size": 14,
        "preferred_driver_username": None,
    }
    # Also alias theme -> theme_name
    defaults["theme"] = defaults["theme_name"]
    save_user_preferences(username, defaults)
    return defaults


def save_user_preferences(username, prefs):
    conn = get_conn()
    c = conn.cursor()

    # accept either "theme" or "theme_name" from callers
    theme_value = prefs.get("theme") or prefs.get("theme_name") or "default"

    c.execute(
        """
        INSERT OR REPLACE INTO user_preferences
        (username, sidebar_color, background_color, button_color,
         button_hover_color, text_color, theme_name, font_size,
         preferred_driver_username)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            username,
            prefs.get("sidebar_color", "#2c3e50"),
            prefs.get("background_color", "#FFEAEC"),
            prefs.get("button_color", "#2c3e50"),
            prefs.get("button_hover_color", "#34495e"),
            prefs.get("text_color", "white"),
            theme_value,
            prefs.get("font_size", 14),
            prefs.get("preferred_driver_username"),
        ),
    )

    conn.commit()
    conn.close()



# RIDES & MATCHING PASSENGERS AND DRIVERS
def create_ride_request(data):
    """
    data = {
        passenger_username,
        area,
        time (string),
        weekday int
    }
    """
    conn = get_conn()
    c = conn.cursor()

    time_sec = time_to_seconds(data["time"])

    try:
        c.execute(
            """
            INSERT INTO rides (passenger_username, area, time, weekday, status)
            VALUES (?, ?, ?, ?, 'pending')
        """,
            (
                data["passenger_username"],
                data["area"],
                time_sec,
                data["weekday"],
            ),
        )

        ride_id = c.lastrowid
        conn.commit()
        return {
            "status": "success",
            "message": "Ride request created successfully",
            "ride_id": ride_id,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        conn.close()


def get_available_drivers(area, weekday, target_seconds):
    """Return list of drivers whose weekly schedule matches within +-10 min."""
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT username, weekly_schedule
        FROM users
        WHERE role='driver' AND area=?
    """,
        (area,),
    )

    drivers = c.fetchall()
    conn.close()

    good = []
    lower = max(0, target_seconds - 600)
    upper = min(86399, target_seconds + 600)

    for username, sched_json in drivers:
        if not sched_json:
            continue

        schedule = json.loads(sched_json)

        # ex: {"Monday": "8:00", "Tuesday": "09:15", ...}
        for day, timestr in schedule.items():
            if weekday_to_int(day) == weekday:
                try:
                    sec = time_to_seconds(timestr)
                except:
                    continue
                if lower <= sec <= upper:
                    good.append(username)

    return good


def accept_ride(ride_id, driver_username, ip=None, port=None):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        UPDATE rides
        SET status='accepted', driver_username=?, driver_ip=?, driver_port=?
        WHERE id=? AND status='pending'
    """,
        (driver_username, ip, port, ride_id),
    )

    conn.commit()
    ok = c.rowcount > 0
    conn.close()

    return ok


def decline_ride(ride_id):
    """Mark a pending ride as declined so it no longer appears in pending lists."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE rides
        SET status='declined'
        WHERE id=? AND status='pending'
        """,
        (ride_id,),
    )
    conn.commit()
    ok = c.rowcount > 0
    conn.close()
    return ok


def get_ride_by_id(ride_id):
    """Return a single ride row as a dict, or None if not found."""
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, passenger_username, area, time, weekday, status,
               driver_username, driver_ip, driver_port
        FROM rides
        WHERE id=?
        """,
        (ride_id,),
    )
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "id": row[0],
        "passenger_username": row[1],
        "area": row[2],
        "time": row[3],
        "weekday": row[4],
        "status": row[5],
        "driver_username": row[6],
        "driver_ip": row[7],
        "driver_port": row[8],
    }


def complete_ride(ride_id, driver_username):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        UPDATE rides
        SET status='completed'
        WHERE id=? AND status='accepted' AND driver_username=?
    """,
        (ride_id, driver_username),
    )

    conn.commit()
    ok = c.rowcount > 0
    conn.close()
    return ok


def get_pending_rides(area):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT id, passenger_username, area, time, weekday
        FROM rides
        WHERE status='pending' AND area=?
    """,
        (area,),
    )

    rows = c.fetchall()
    conn.close()

    return [
        {
            "id": r[0],
            "passenger_username": r[1],
            "area": r[2],
            "time": r[3],
            "weekday": r[4],
        }
        for r in rows
    ]


def get_ride_history(username, role):
    conn = get_conn()
    c = conn.cursor()

    if role == "passenger":
        c.execute(
            """
            SELECT id, passenger_username, area, time, weekday, status,
                   driver_username, driver_ip, driver_port
            FROM rides
            WHERE passenger_username=?
            """,
            (username,),
        )
    elif role == "driver":
        c.execute(
            """
            SELECT id, passenger_username, area, time, weekday, status,
                   driver_username, driver_ip, driver_port
            FROM rides
            WHERE driver_username=?
            """,
            (username,),
        )
    else:
        conn.close()
        return {"status": "error", "message": "Invalid role"}

    rows = c.fetchall()

    # Separate cursor for ratings lookups
    c2 = conn.cursor()

    rides_out = []
    for r in rows:
        ride_id = r[0]
        passenger_username = r[1]
        area = r[2]
        time_val = r[3]
        weekday = r[4]
        status = r[5]
        driver_username = r[6]
        driver_ip = r[7]
        driver_port = r[8]

        # Determine who is "me" and who is "other" for per-ride ratings
        if role == "passenger":
            me = username
            other = driver_username
        else:
            me = username
            other = passenger_username

        my_rating = None
        their_rating = None

        if other:
            # Rating I gave them (if any)
            c2.execute(
                """
                SELECT score
                FROM ratings
                WHERE ride_id=? AND rater_username=? AND ratee_username=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ride_id, me, other),
            )
            row_my = c2.fetchone()
            if row_my and row_my[0] is not None:
                my_rating = float(row_my[0])

            # Rating they gave me (if any)
            c2.execute(
                """
                SELECT score
                FROM ratings
                WHERE ride_id=? AND rater_username=? AND ratee_username=?
                ORDER BY id DESC
                LIMIT 1
                """,
                (ride_id, other, me),
            )
            row_their = c2.fetchone()
            if row_their and row_their[0] is not None:
                their_rating = float(row_their[0])

        rides_out.append(
            {
                "id": ride_id,
                "passenger_username": passenger_username,
                "area": area,
                "time": time_val,
                "weekday": weekday,
                "status": status,
                "driver_username": driver_username,
                "driver_ip": driver_ip,
                "driver_port": driver_port,
                # Per-ride rating fields used by the GUI history page
                "my_rating": my_rating,
                "their_rating": their_rating,
            }
        )

    conn.close()
    return {"status": "success", "rides": rides_out}



# PREMIUM: LIST DRIVERS (FOR SEARCHING/BROWSING)
def list_drivers(area: str = None):
    """
    Return drivers (optionally filtered by area) with their average rating.
    The server layer will add status info.
    """
    conn = get_conn()
    c = conn.cursor()

    if area:
        c.execute(
            """
            SELECT username, name, area
            FROM users
            WHERE role='driver' AND area=?
            """,
            (area,),
        )
    else:
        c.execute(
            """
            SELECT username, name, area
            FROM users
            WHERE role='driver'
            """
        )

    rows = c.fetchall()

    drivers = []
    for username, name, area_val in rows:
        c.execute(
            "SELECT AVG(score) FROM ratings WHERE ratee_username=?",
            (username,),
        )
        avg = c.fetchone()[0]
        rating = None if avg is None else round(float(avg), 2)

        drivers.append(
            {
                "username": username,
                "name": name,
                "area": area_val,
                "rating": rating,
            }
        )

    conn.close()
    return {"status": "success", "drivers": drivers}



# PREMIUM: SCHEDULED RIDES
def find_drivers_for_datetime(area: str, date_str: str, time_str: str):
    """
    Given an area + calendar date + time string, return drivers whose weekly_schedule matches that weekday/time, including
    rating info.

    This does NOT check whether drivers are currently online; it's for future scheduling.
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        raise ValueError(f"Invalid date format: {date_str} (expected YYYY-MM-DD)")

    weekday = dt.weekday()
    target_seconds = time_to_seconds(time_str)

    matched_usernames = set(get_available_drivers(area, weekday, target_seconds))
    if not matched_usernames:
        return []

    # Reuse list_drivers to enrich with name + rating
    all_drivers_dict = list_drivers(area)
    all_drivers = all_drivers_dict.get("drivers", [])

    return [d for d in all_drivers if d.get("username") in matched_usernames]


def create_scheduled_ride(data: dict):
    """
    Insert a scheduled ride.

    data = {
        passenger_username,
        driver_username,
        area,
        date (YYYY-MM-DD),
        time (string, e.g. '08:30')
    }

    Status is set to 'scheduled' by default.
    """
    required = ["passenger_username", "driver_username", "area", "date", "time"]
    for k in required:
        if not data.get(k):
            return {"status": "error", "message": f"Missing field: {k}"}

    date_str = data["date"]
    time_str = data["time"]

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception as e:
        return {"status": "error", "message": f"Invalid date: {e}"}

    weekday = dt.weekday()

    try:
        time_sec = time_to_seconds(time_str)
    except Exception as e:
        return {"status": "error", "message": f"Invalid time: {e}"}

    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute(
            """
            INSERT INTO scheduled_rides
            (passenger_username, driver_username, area, date, time, weekday, status)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled')
            """,
            (
                data["passenger_username"],
                data["driver_username"],
                data["area"],
                date_str,
                time_sec,
                weekday,
            ),
        )
        conn.commit()
        scheduled_ride_id = c.lastrowid
        # expose both scheduled_ride_id and ride_id so the GUI can show the ID
        return {
            "status": "success",
            "scheduled_ride_id": scheduled_ride_id,
            "ride_id": scheduled_ride_id,
            "message": "Scheduled ride created.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def get_scheduled_ride(ride_id: int):
    """
    Return a single scheduled ride as a dict, or None if not found.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        SELECT id, passenger_username, driver_username,
               area, date, time, weekday, status
        FROM scheduled_rides
        WHERE id=?
        """,
        (ride_id,),
    )
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    return {
        "id": row[0],
        "passenger_username": row[1],
        "driver_username": row[2],
        "area": row[3],
        "date": row[4],
        "time": row[5],
        "weekday": row[6],
        "status": row[7],
    }


def get_scheduled_rides(username: str, role: str):
    """
    Return scheduled rides for the given user & role ("passenger" or "driver")
    """
    conn = get_conn()
    c = conn.cursor()

    if role == "passenger":
        where = "passenger_username=?"
    elif role == "driver":
        where = "driver_username=?"
    else:
        conn.close()
        return {"status": "error", "message": "Invalid role"}

    c.execute(
        f"""
        SELECT id, passenger_username, driver_username,
               area, date, time, weekday, status
        FROM scheduled_rides
        WHERE {where}
        ORDER BY date, time
        """,
        (username,),
    )
    rows = c.fetchall()
    conn.close()

    rides = []
    for r in rows:
        rides.append(
            {
                "id": r[0],
                "passenger_username": r[1],
                "driver_username": r[2],
                "area": r[3],
                "date": r[4],
                "time": r[5],
                "weekday": r[6],
                "status": r[7],
            }
        )

    return {"status": "success", "rides": rides}


def update_scheduled_ride_status(ride_id: int, status: str) -> bool:
    """
    Update the status of a scheduled ride. Returns True if a row was updated.
    """
    conn = get_conn()
    c = conn.cursor()
    c.execute(
        """
        UPDATE scheduled_rides
        SET status=?
        WHERE id=?
        """,
        (status, ride_id),
    )
    conn.commit()
    ok = c.rowcount > 0
    conn.close()
    return ok



# RATINGS
def submit_rating(data):
    """
    data = {
        ride_id,
        rater_username,
        ratee_username,
        score,
        comment
    }
    """
    conn = get_conn()
    c = conn.cursor()

    try:
        c.execute(
            """
            INSERT INTO ratings (ride_id, rater_username, ratee_username, score, comment)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                data["ride_id"],
                data["rater_username"],
                data["ratee_username"],
                data["score"],
                data.get("comment", ""),
            ),
        )

        conn.commit()
        return {"status": "success"}

    except Exception as e:
        return {"status": "error", "message": str(e)}

    finally:
        conn.close()


def get_average_rating(username):
    conn = get_conn()
    c = conn.cursor()

    c.execute(
        """
        SELECT AVG(score) FROM ratings WHERE ratee_username=?
    """,
        (username,),
    )

    avg = c.fetchone()[0]
    conn.close()

    return None if avg is None else round(float(avg), 2)
