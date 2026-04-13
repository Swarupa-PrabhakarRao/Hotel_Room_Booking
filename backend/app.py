from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def serve_file(path):
    return app.send_static_file(path)

# MongoDB Configuration
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/hotel_db')
client = MongoClient(mongo_uri)
db = client.get_default_database(default='hotel_db')
users_collection = db['users']
rooms_collection = db['rooms']
bookings_collection = db['bookings']

# --- HELPER FUNCTIONS ---
def format_room(room):
    room['roomId'] = str(room['_id'])
    del room['_id']
    return room

def format_booking(booking):
    booking['bookingId'] = str(booking['_id'])
    booking['roomId'] = str(booking['roomId'])
    del booking['_id']
    return booking

# --- ROUTES ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    if not all([name, email, password]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
    if users_collection.find_one({'email': email}):
        return jsonify({'success': False, 'message': 'Email already registered'}), 400
        
    user_doc = {
        'name': name,
        'email': email,
        'password_hash': generate_password_hash(password),
        'role': 'user'
    }
    users_collection.insert_one(user_doc)
    return jsonify({'success': True, 'message': 'User registered successfully'})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    user = users_collection.find_one({'email': email})
    if user and check_password_hash(user['password_hash'], password):
        return jsonify({
            'success': True, 
            'user': {'name': user['name'], 'email': user['email'], 'role': user['role']}
        })
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/rooms', methods=['GET', 'POST'])
def handle_rooms():
    if request.method == 'GET':
        rooms = list(rooms_collection.find())
        return jsonify({'success': True, 'data': [format_room(r) for r in rooms]})
        
    elif request.method == 'POST':
        # Adding a room (admin feature)
        data = request.json
        new_room = {
            'roomNumber': data.get('roomNumber'),
            'type': data.get('type'),
            'price': data.get('price'),
            'isAvailable': data.get('isAvailable', True),
            'description': data.get('description', ''),
            'maxOccupancy': data.get('maxOccupancy', 2)
        }
        if rooms_collection.find_one({'roomNumber': new_room['roomNumber']}):
            return jsonify({'success': False, 'message': 'Room number already exists'}), 400
            
        rooms_collection.insert_one(new_room)
        return jsonify({'success': True, 'message': 'Room added'})

@app.route('/api/rooms/<room_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_room(room_id):
    try:
        obj_id = ObjectId(room_id)
    except:
        return jsonify({'success': False, 'message': 'Invalid room ID'}), 400

    if request.method == 'GET':
        room = rooms_collection.find_one({'_id': obj_id})
        if room:
            return jsonify({'success': True, 'data': format_room(room)})
        return jsonify({'success': False, 'message': 'Room not found'}), 404
        
    elif request.method == 'PUT':
        data = request.json
        update_data = {
            'price': data.get('price'),
            'isAvailable': data.get('isAvailable'),
            'description': data.get('description')
        }
        # filter out None values if they weren't provided
        update_data = {k:v for k,v in update_data.items() if v is not None}
        
        rooms_collection.update_one({'_id': obj_id}, {'$set': update_data})
        return jsonify({'success': True, 'message': 'Room updated'})
        
    elif request.method == 'DELETE':
        rooms_collection.delete_one({'_id': obj_id})
        return jsonify({'success': True, 'message': 'Room deleted'})

@app.route('/api/bookings', methods=['GET', 'POST'])
def handle_bookings():
    if request.method == 'POST':
        data = request.json
        room_id_str = data.get('roomId')
        user_name = data.get('userName')
        user_email = data.get('userEmail')
        from_date_str = data.get('fromDate')
        to_date_str = data.get('toDate')
        
        if not all([room_id_str, user_name, user_email, from_date_str, to_date_str]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
            
        try:
            room_id = ObjectId(room_id_str)
        except:
            return jsonify({'success': False, 'message': 'Invalid room ID'}), 400
            
        room = rooms_collection.find_one({'_id': room_id})
        if not room or not room.get('isAvailable', True):
            return jsonify({'success': False, 'message': 'Room unavailable'}), 400
            
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
        
        days = (to_date - from_date).days
        if days <= 0: days = 1
        total_price = room.get('price', 0) * days
        
        booking_doc = {
            'roomId': room_id,
            'roomNumber': room.get('roomNumber'),
            'userName': user_name,
            'userEmail': user_email,
            'fromDate': from_date_str,
            'toDate': to_date_str,
            'totalPrice': total_price,
            'status': 'confirmed',
            'createdAt': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Mark room as unavailable
        rooms_collection.update_one({'_id': room_id}, {'$set': {'isAvailable': False}})
        result = bookings_collection.insert_one(booking_doc)
        
        return_booking = format_booking(bookings_collection.find_one({'_id': result.inserted_id}))
        return jsonify({'success': True, 'message': 'Booking confirmed!', 'data': return_booking})
        
    elif request.method == 'GET':
        email = request.args.get('email')
        query = {'userEmail': email} if email else {}
        bookings = list(bookings_collection.find(query))
        return jsonify({'success': True, 'data': [format_booking(b) for b in bookings]})

@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def cancel_booking(booking_id):
    try:
        obj_id = ObjectId(booking_id)
    except:
        return jsonify({'success': False, 'message': 'Invalid booking ID'}), 400
        
    booking = bookings_collection.find_one({'_id': obj_id})
    if booking:
        # Relese room
        rooms_collection.update_one({'_id': booking['roomId']}, {'$set': {'isAvailable': True}})
        bookings_collection.update_one({'_id': obj_id}, {'$set': {'status': 'cancelled'}})
        return jsonify({'success': True, 'message': 'Booking cancelled'})
        
    return jsonify({'success': False, 'message': 'Booking not found'}), 404

def seed_db():
    if rooms_collection.count_documents({}) == 0:
        print("Seeding MongoDB...")
        rooms = [
            {'roomNumber': 101, 'type': 'Single', 'price': 100.0, 'maxOccupancy': 1, 'isAvailable': True, 'description': ''},
            {'roomNumber': 102, 'type': 'Double', 'price': 150.0, 'maxOccupancy': 2, 'isAvailable': True, 'description': ''},
            {'roomNumber': 201, 'type': 'Deluxe', 'price': 250.0, 'maxOccupancy': 3, 'isAvailable': True, 'description': ''},
            {'roomNumber': 301, 'type': 'Suite',  'price': 450.0, 'maxOccupancy': 4, 'isAvailable': True, 'description': 'Luxury suite with ocean view'}
        ]
        rooms_collection.insert_many(rooms)
        
        if users_collection.count_documents({'email': 'admin@grandazure.com'}) == 0:
            admin = {
                'name': 'Admin',
                'email': 'admin@grandazure.com',
                'password_hash': generate_password_hash('admin123'),
                'role': 'admin'
            }
            users_collection.insert_one(admin)
            
        print("Database seeded!")

if __name__ == '__main__':
    seed_db()
    print("🚀 Flask Server with MongoDB running on port 5000")
    app.run(port=5000, debug=True)
