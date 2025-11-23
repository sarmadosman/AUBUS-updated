"""
client/cli_client.py

Simple command-line client for the AUBus JSON server.
Uses client.api_client as the underlying transport.

This is mainly a developer / debugging tool and a reference for how the GUI
should talk to the backend.
"""

import sys
from typing import Optional

from . import api_client


def prompt(text: str, default: Optional[str] = None) -> str:
    if default is not None:
        val = input(f"{text} [{default}]: ").strip()
        return val or default
    return input(f"{text}: ").strip()


def print_header(title: str) -> None:
    print("\n" + "=" * 60)
    print(f"{title}")
    print("=" * 60)


def handle_register() -> None:
    print_header("Register new user")
    username = prompt("Username")
    password = prompt("Password")
    role = ""
    while role not in ("driver", "passenger"):
        role = prompt("Role (driver/passenger)").lower()
    area = prompt("Area (e.g. Hamra)")

    weekly_schedule = None
    if role == "driver":
        print("Enter departure time for each day (HH:MM, blank to skip day).")
        days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        schedule = {}
        for d in days:
            t = prompt(f"{d} time", default="").strip()
            if t:
                schedule[d] = t
        if schedule:
            weekly_schedule = schedule

    resp = api_client.register_user(
        username=username,
        password=password,
        area=area,
        role=role,
        weekly_schedule=weekly_schedule,
    )
    print("Response:", resp)


def handle_request_ride(current_username: str, current_area: str) -> None:
    print_header("Request a ride (passenger)")
    print(f"You are logged in as passenger {current_username}, area={current_area}")
    time_str = prompt("Pickup time (e.g. 08:30 or 08:30 AM)")
    resp = api_client.create_ride(
        passenger_username=current_username,
        area=current_area,
        time_str=time_str,
    )
    print("Response:", resp)


def handle_list_pending(area: str) -> None:
    print_header("Pending rides (driver)")
    resp = api_client.get_pending_rides(area)
    if resp.get("status") != "success":
        print("Error:", resp.get("message"))
        return
    rides = resp.get("rides", [])
    if not rides:
        print("No pending rides in your area.")
        return
    for r in rides:
        print(
            f"ID={r.get('id')} | passenger={r.get('passenger_username')} "
            f"| area={r.get('area')} | time={r.get('time')}"
        )


def handle_accept_ride(current_username: str) -> None:
    print_header("Accept a ride (driver)")
    ride_id_str = prompt("Ride ID to accept")
    try:
        ride_id = int(ride_id_str)
    except ValueError:
        print("Invalid ride ID.")
        return

    # For CLI demo we just ask user to supply IP + port where their P2P chat
    # server is listening (e.g., 0.0.0.0:6000 on the driver machine).
    driver_ip = prompt("Your P2P IP (visible to passenger)", default="127.0.0.1")
    driver_port_str = prompt("Your P2P port", default="6000")
    try:
        driver_port = int(driver_port_str)
    except ValueError:
        print("Invalid port.")
        return

    resp = api_client.accept_ride(
        ride_id=ride_id,
        driver_username=current_username,
        driver_ip=driver_ip,
        driver_port=driver_port,
    )
    print("Response:", resp)


def handle_history(current_username: str, role: str) -> None:
    print_header("Ride history")
    resp = api_client.get_ride_history(current_username, role)
    if resp.get("status") != "success":
        print("Error:", resp.get("message"))
        return
    rides = resp.get("rides", [])
    if not rides:
        print("No rides found.")
        return
    for r in rides:
        print(
            f"ID={r.get('id')} | passenger={r.get('passenger_username')} | "
            f"driver={r.get('driver_username')} | area={r.get('area')} | "
            f"time={r.get('time')} | status={r.get('status')} | "
            f"driver_ip={r.get('driver_ip')} | driver_port={r.get('driver_port')}"
        )


def handle_submit_rating(current_username: str) -> None:
    print_header("Submit rating")
    ride_id_str = prompt("Ride ID")
    ratee_username = prompt("User you are rating")
    score_str = prompt("Score (1-5)")
    comment = prompt("Comment (optional)", default="")

    try:
        ride_id = int(ride_id_str)
        score = int(score_str)
    except ValueError:
        print("Invalid ride ID or score.")
        return

    resp = api_client.submit_rating(
        ride_id=ride_id,
        rater_username=current_username,
        ratee_username=ratee_username,
        score=score,
        comment=comment,
    )
    print("Response:", resp)


def handle_get_rating() -> None:
    print_header("Get rating")
    username = prompt("Username to check rating for")
    resp = api_client.get_rating(username)
    if resp.get("status") != "success":
        print("Error:", resp.get("message"))
        return
    print(f"Average rating for {username}: {resp.get('rating')}")


def main() -> None:
    print_header("AUBus CLI client")

    current_username: Optional[str] = None
    current_role: Optional[str] = None
    current_area: Optional[str] = None

    while True:
        if current_username is None:
            print("\nYou are not logged in.")
            print("Options:")
            print("  1) Register new user")
            print("  2) Login")
            print("  q) Quit")
            choice = input("> ").strip().lower()

            if choice == "1":
                handle_register()
            elif choice == "2":
                print_header("Login")
                username = prompt("Username")
                password = prompt("Password")
                resp = api_client.login_user(username, password)
                if resp.get("status") == "success":
                    current_username = resp.get("username", username)
                    current_role = resp.get("role")
                    current_area = resp.get("area")
                    print(
                        f"Logged in as {current_username} "
                        f"({current_role}) in area {current_area}"
                    )
                else:
                    print("Login failed:", resp.get("message"))
            elif choice == "q":
                print("Bye.")
                sys.exit(0)
            else:
                print("Invalid choice.")
        else:
            print(f"\nLogged in as {current_username} (role={current_role}, area={current_area})")
            print("Options:")
            if current_role == "passenger":
                print("  1) Request a ride")
            if current_role == "driver":
                print("  2) List pending rides in my area")
                print("  3) Accept a ride")
            print("  4) Show my ride history")
            print("  5) Submit a rating")
            print("  6) Get a user's rating")
            print("  l) Logout")
            print("  q) Quit")
            choice = input("> ").strip().lower()

            if choice == "1" and current_role == "passenger":
                handle_request_ride(current_username, current_area)
            elif choice == "2" and current_role == "driver":
                handle_list_pending(current_area)
            elif choice == "3" and current_role == "driver":
                handle_accept_ride(current_username)
            elif choice == "4":
                handle_history(current_username, current_role)
            elif choice == "5":
                handle_submit_rating(current_username)
            elif choice == "6":
                handle_get_rating()
            elif choice == "l":
                print("Logging out.")
                current_username = None
                current_role = None
                current_area = None
            elif choice == "q":
                if current_username:
                    api_client.disconnect(current_username)
                print("Bye.")
                sys.exit(0)
            else:
                print("Invalid choice or not allowed for your role.")


if __name__ == "__main__":
    main()
