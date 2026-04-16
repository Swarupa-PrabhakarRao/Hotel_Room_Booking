# Grand Azure Hotel & Resort Booking System

A full-stack web application for managing hotel room bookings, user accounts, and administrative tasks.

## Features
- **User Authentication:** Sign up and log in roles (User and Admin).
- **Room Browsing:** View available suites, single, double, and deluxe rooms with dynamic filtering.
- **Booking Engine:** Book a room securely, check dashboards for active/canceled bookings.
- **Admin Panel:** Add, edit, or remove rooms and cancel bookings.
- **Modern UI:** Built with plain HTML, CSS (glassmorphism UI), and vanilla JavaScript.
- **Cloud Database:** Connects to MongoDB Atlas to persist users, rooms, and bookings.

## Tech Stack
- **Frontend:** HTML5, CSS3, Vanilla JavaScript
- **Backend:** Python, Flask, Flask-CORS
- **Database:** MongoDB (using PyMongo)

## Setup & Running Locally
1. Navigate to the `backend` directory.
2. Install dependencies: `pip install -r requirements.txt`
3. Run the application: `python app.py`
4. The system will be available at `http://localhost:5000/`.