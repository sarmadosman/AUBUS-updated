📄 API.md — AUBus JSON Protocol Specification
Overview

AUBus uses a simple TCP JSON protocol.
The client sends JSON requests to the backend.
The backend responds with JSON.
Some messages (notifications) are pushed to the client at any time.

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


Additionally, the server may send asynchronous notifications such as:

new_ride

ride_accepted

1. User Actions
1.1 Register (action: register)

Request:

{
  "action": "register",
  "username": "sara",
  "password": "123",
  "name": "Sara",
  "email": "sara@example.com",
  "area": "Beirut",
  "role": "driver",
  "weekly_schedule": {
    "Monday": "08:00",
    "Wednesday": "09:15"
  }
}


Response:

{
  "status": "success",
  "message": "User registered successfully"
}

1.2 Login (action: login)

Request:

{
  "action": "login",
  "username": "sara",
  "password": "123"
}


Response:

{
  "status": "success",
  "message": "Login successful",
  "username": "sara",
  "area": "Beirut",
  "role": "driver",
  "weekly_schedule": {...},
  "preferences": {...}
}

2. Ride System
2.1 Create Ride (action: create_ride)

Request:

{
  "action": "create_ride",
  "passenger_username": "ali",
  "area": "Beirut",
  "time": "08:30"
}


Response:

{
  "status": "success",
  "ride_id": 12,
  "message": "Ride request created successfully"
}


Triggers real-time notification to drivers:

{
  "action": "new_ride",
  "ride_id": 12,
  "passenger_username": "ali",
  "area": "Beirut",
  "time": 30600,
  "weekday": 0
}

2.2 Accept Ride (action: accept_ride)

Request:

{
  "action": "accept_ride",
  "ride_id": 12,
  "username": "sara",
  "driver_ip": "127.0.0.1",
  "driver_port": 6000
}


Response:

{
  "status": "success",
  "message": "Ride accepted."
}


Triggers passenger real-time notification:

{
  "action": "ride_accepted",
  "ride_id": 12,
  "driver_username": "sara",
  "driver_ip": "127.0.0.1",
  "driver_port": 6000
}

2.3 Get Pending Rides (action: get_pending_rides)

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
      "passenger_username": "ali",
      "area": "Beirut",
      "time": 30600,
      "weekday": 0
    }
  ]
}

2.4 Complete Ride (action: complete_ride)

Request:

{
  "action": "complete_ride",
  "ride_id": 12,
  "username": "sara"
}


Response:

{
  "status": "success",
  "message": "Ride completed."
}

2.5 Ride History (action: get_ride_history)

Request:

{
  "action": "get_ride_history",
  "username": "ali",
  "role": "passenger"
}


Response:

{
  "status": "success",
  "rides": [...]
}

3. Ratings
3.1 Submit Rating (action: submit_rating)

Request:

{
  "action": "submit_rating",
  "ride_id": 12,
  "rater_username": "ali",
  "ratee_username": "sara",
  "score": 5,
  "comment": "Great driver"
}


Response:

{
  "status": "success"
}

3.2 Get Rating (action: get_rating)

Request:

{
  "action": "get_rating",
  "username": "sara"
}


Response:

{
  "status": "success",
  "rating": 4.5
}

4. Preferences
4.1 Get Preferences (action: get_preferences)

Response:

{
  "status": "success",
  "preferences": {...}
}

4.2 Save Preferences (action: save_preferences)

Request:

{
  "action": "save_preferences",
  "username": "sara",
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


The GUI must listen on a persistent socket to receive these.