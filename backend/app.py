from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid
from pymongo import MongoClient

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# ✅ MONGODB CONNECTION
MONGO_URI = "mongodb+srv://Swarupa:Swarupa123@cluster0.mzx6uba.mongodb.net/myDatabase?retryWrites=true&w=majority"
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['myDatabase']
    users_collection = db['users']
    rooms_collection = db['rooms']
    bookings_collection = db['bookings']
    
    # Ensure admin exists
    if not users_collection.find_one({'email': 'swarupavemulapallii@gmail.com'}):
        users_collection.insert_one({
            'email': 'swarupavemulapallii@gmail.com',
            'name': 'Admin Swarupa',
            'password': generate_password_hash('123456'),
            'role': 'admin'
        })
    print("✅ Successfully connected to MongoDB")
except Exception as e:
    print(f"❌ Failed to connect to MongoDB: {e}")

# ------------------ FRONTEND ROUTES ------------------
@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def serve_file(path):
    return app.send_static_file(path)

# ------------------ AUTH ------------------

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')

    if not all([name, email, password]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400

    if users_collection.find_one({'email': email}):
        return jsonify({'success': False, 'message': 'Email already exists'}), 400

    users_collection.insert_one({
        'email': email,
        'name': name,
        'password': generate_password_hash(password),
        'role': 'user'
    })

    return jsonify({'success': True, 'message': 'User registered successfully'})


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'user')

    user = users_collection.find_one({'email': email})

    if user and check_password_hash(user['password'], password) and user['role'] == role:
        return jsonify({
            'success': True,
            'user': {
                'name': user['name'],
                'email': email,
                'role': user['role']
            }
        })

    return jsonify({'success': False, 'message': 'Invalid credentials or role'}), 401


# ------------------ ROOMS ------------------

@app.route('/api/rooms', methods=['GET', 'POST'])
def handle_rooms():
    if request.method == 'GET':
        rooms = list(rooms_collection.find({}, {'_id': 0}))
        return jsonify({'success': True, 'data': rooms})

    elif request.method == 'POST':
        data = request.json

        if rooms_collection.find_one({'roomNumber': data.get('roomNumber')}):
            return jsonify({'success': False, 'message': 'Room already exists'}), 400

        room_id = uuid.uuid4().hex

        room_data = {
            'roomId': room_id,
            'roomNumber': data.get('roomNumber'),
            'type': data.get('type'),
            'price': int(data.get('price', 0)),
            'isAvailable': data.get('isAvailable', True),
            'description': data.get('description', ''),
            'maxOccupancy': int(data.get('maxOccupancy', 2))
        }
        rooms_collection.insert_one(room_data)

        return jsonify({'success': True, 'message': 'Room added'})


@app.route('/api/rooms/<room_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_room(room_id):
    room = rooms_collection.find_one({'roomId': room_id}, {'_id': 0})

    if not room:
        return jsonify({'success': False, 'message': 'Room not found'}), 404

    if request.method == 'GET':
        return jsonify({'success': True, 'data': room})

    elif request.method == 'PUT':
        data = request.json
        price = data.get('price')
        is_available = data.get('isAvailable')
        desc = data.get('description')
        
        update_fields = {}
        if price is not None: update_fields['price'] = int(price)
        if is_available is not None: update_fields['isAvailable'] = is_available
        if desc is not None: update_fields['description'] = desc

        if update_fields:
            rooms_collection.update_one({'roomId': room_id}, {'$set': update_fields})
            
        return jsonify({'success': True, 'message': 'Room updated'})

    elif request.method == 'DELETE':
        rooms_collection.delete_one({'roomId': room_id})
        return jsonify({'success': True, 'message': 'Room deleted'})


# ------------------ BOOKINGS ------------------

@app.route('/api/bookings', methods=['GET', 'POST'])
def handle_bookings():
    if request.method == 'POST':
        data = request.json

        room_id = data.get('roomId')
        room = rooms_collection.find_one({'roomId': room_id})

        if not room or not room.get('isAvailable'):
            return jsonify({'success': False, 'message': 'Room unavailable'}), 400

        from_date = datetime.strptime(data.get('fromDate'), '%Y-%m-%d')
        to_date = datetime.strptime(data.get('toDate'), '%Y-%m-%d')

        days = max((to_date - from_date).days, 1)
        total_price = room['price'] * days

        booking_id = uuid.uuid4().hex

        booking = {
            'bookingId': booking_id,
            'roomId': room_id,
            'roomNumber': room['roomNumber'],
            'userName': data.get('userName'),
            'userEmail': data.get('userEmail'),
            'fromDate': data.get('fromDate'),
            'toDate': data.get('toDate'),
            'totalPrice': total_price,
            'status': 'confirmed',
            'createdAt': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }

        bookings_collection.insert_one(booking)
        rooms_collection.update_one({'roomId': room_id}, {'$set': {'isAvailable': False}})

        return jsonify({'success': True, 'message': 'Booking confirmed', 'data': booking})

    elif request.method == 'GET':
        bookings_cursor = bookings_collection.find({}, {'_id': 0})
        return jsonify({'success': True, 'data': list(bookings_cursor)})


@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def cancel_booking(booking_id):
    booking = bookings_collection.find_one({'bookingId': booking_id})

    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404

    # make room available again
    rooms_collection.update_one({'roomId': booking['roomId']}, {'$set': {'isAvailable': True}})
    bookings_collection.update_one({'bookingId': booking_id}, {'$set': {'status': 'cancelled'}})

    return jsonify({'success': True, 'message': 'Booking cancelled'})


# ------------------ RUN ------------------

if __name__ == '__main__':
    print("Flask running with MongoDB on http://localhost:5000")
    app.run(port=5000, debug=True)