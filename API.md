API.md:

Overview:

AUBus uses a simple TCP JSON protocol.
The client sends JSON requests to the backend.
The backend responds with JSON.
Some messages are pushed to the client at any time.

Server:
HOST = 127.0.0.1
PORT = 5555


Each request is:
{
  "action": "<action_name>",
  ... fields ...
}


Each response is:
{
  "status": "success" | "error",
  "message": "...",
  ... data ...
}

Additionally, the server may send notifications like new_ride and ride_accepted

1. User Actions:
- Register (action: register)
Request:
{
  "action": "register",
  "username": "sarmad",
  "password": "123",
  "name": "Sarmad",
  "email": "sarmad@aub.edu.lb",
  "area": "Beirut",
  "role": "driver",
  "weekly_schedule": {
    "Monday": "10:00",
    "Tuesday": "9:30",
    "Wednesday": "09:15"
  }
}
Response:
{
  "status": "success",
  "message": "User registered successfully"
}

- Login (action: login)
Request:

{
  "action": "login",
  "username": "sarmad",
  "password": "123"
}
Response:

{
  "status": "success",
  "message": "Login successful",
  "username": "sarmad",
  "area": "Beirut",
  "role": "driver",
  "weekly_schedule": {...},
  "preferences": {...}
}

2. Ride System
- Create Ride (action: create_ride)
Request:
{
  "action": "create_ride",
  "passenger_username": "rabih",
  "area": "Beirut",
  "time": "08:30"
}

Response:
{
  "status": "success",
  "ride_id": 12,
  "message": "Ride request created successfully"
}

Real-time notification to drivers:
{
  "action": "new_ride",
  "ride_id": 12,
  "passenger_username": "rabih",
  "area": "Beirut",
  "time": 30600,
  "weekday": 0
}

- Accept Ride (action: accept_ride)
Request:
{
  "action": "accept_ride",
  "ride_id": 12,
  "username": "sarmad",
  "driver_ip": "127.0.0.1",
  "driver_port": 6000
}

Response:
{
  "status": "success",
  "message": "Ride accepted."
}

Real-time notification to passenger:
{
  "action": "ride_accepted",
  "ride_id": 12,
  "driver_username": "sarmad",
  "driver_ip": "127.0.0.1",
  "driver_port": 6000
}

- Get Pending Rides (action: get_pending_rides)
Request:
{
  "action": "get_pending_rides",
  "area": "Beirut"
}

Response:
{
  "status": "success",
  "rides": [
    {
      "id": 12,
      "passenger_username": "rabih",
      "area": "Beirut",
      "time": 30600,
      "weekday": 0
    }
  ]
}

- Complete Ride (action: complete_ride)
Request:
{
  "action": "complete_ride",
  "ride_id": 12,
  "username": "sarmad"
}

Response:
{
  "status": "success",
  "message": "Ride completed."
}

- Ride History (action: get_ride_history)
Request:
{
  "action": "get_ride_history",
  "username": "rabih",
  "role": "passenger"
}

Response:
{
  "status": "success",
  "rides": [...]
}

3. Ratings
- Submit Rating (action: submit_rating)
Request:
{
  "action": "submit_rating",
  "ride_id": 12,
  "rater_username": "rabih",
  "ratee_username": "sarmad",
  "score": 5,
  "comment": "Great driver"
}

Response:
{
  "status": "success"
}

- Get Rating (action: get_rating)
Request:
{
  "action": "get_rating",
  "username": "sarmad"
}

Response:
{
  "status": "success",
  "rating": 4.5
}

4. Preferences
- Get Preferences (action: get_preferences)
Response:
{
  "status": "success",
  "preferences": {...}
}

- Save Preferences (action: save_preferences)
Request:
{
  "action": "save_preferences",
  "username": "sarmad",
  "preferences": { ... }
}

Response:
{
  "status": "success"
}

5. Disconnect (action: disconnect)
Response:
{
  "status": "success",
  "message": "Disconnected."
}

6. Real-Time Notifications
Sent to drivers
{
  "action": "new_ride",
  ...
}

Sent to passengers
{
  "action": "ride_accepted",
  ...
}

The GUI must listen on a persistent socket to receive these, which is why we use TCP (supports persistent connection).