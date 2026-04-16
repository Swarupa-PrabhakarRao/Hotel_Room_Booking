from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid
import boto3
import random
from boto3.dynamodb.conditions import Key

app = Flask(__name__, static_folder='../frontend', static_url_path='')
CORS(app)

# ✅ AWS DYNAMODB & SNS (IAM Role handled automatically by boto3)
try:
    dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
    sns_client = boto3.client('sns', region_name='us-east-1')

    # Tables - Requires 'Users', 'Rooms', 'Bookings' to be created in DynamoDB
    users_table = dynamodb.Table('Users')
    rooms_table = dynamodb.Table('Rooms')
    bookings_table = dynamodb.Table('Bookings')

    print("✅ Successfully initialized AWS Boto3 Services")
except Exception as e:
    print(f"❌ Failed to initialize AWS Boto3: {e}")

# In-Memory OTP Store mapping email -> OTP string
# For production at scale, this should go to ElastiCache / Redis or DynamoDB with TTL.
otp_store = {}


# ------------------ FRONTEND ROUTES ------------------
@app.route('/')
def serve_index():
    return app.send_static_file('index.html')

@app.route('/<path:path>')
def serve_file(path):
    return app.send_static_file(path)


# ------------------ AUTH & OTP ------------------

@app.route('/api/auth/send-otp', methods=['POST'])
def send_otp():
    """Generates an OTP and sends it via SNS to the provided phone number."""
    data = request.json
    email = data.get('email')
    phone = data.get('phone')

    if not email or not phone:
        return jsonify({'success': False, 'message': 'Email and Phone are required.'}), 400
    
    # Check if user already exists
    response = users_table.get_item(Key={'email': email})
    if 'Item' in response:
        return jsonify({'success': False, 'message': 'Email already exists'}), 400

    otp = str(random.randint(100000, 999999))
    otp_store[email] = otp

    try:
        sns_client.publish(
            PhoneNumber=phone,
            Message=f'Your Grand Azure verification OTP is: {otp}'
        )
        return jsonify({'success': True, 'message': 'OTP sent successfully'})
    except Exception as e:
        print("SNS Error:", str(e))
        return jsonify({'success': False, 'message': 'Failed to send OTP via SMS. Ensure correct format (e.g. +1234567890).'}), 500


@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    otp = data.get('otp')

    if not all([name, email, password, otp]):
        return jsonify({'success': False, 'message': 'Missing required fields or OTP'}), 400

    # Verify OTP
    if otp_store.get(email) != otp:
        return jsonify({'success': False, 'message': 'Invalid OTP'}), 400

    # Clear OTP
    del otp_store[email]

    # Verify user doesn't already exist
    response = users_table.get_item(Key={'email': email})
    if 'Item' in response:
        return jsonify({'success': False, 'message': 'Email already exists'}), 400

    users_table.put_item(
        Item={
            'email': email,
            'name': name,
            'password': generate_password_hash(password),
            'role': 'user'
        }
    )

    return jsonify({'success': True, 'message': 'User registered successfully'})


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'user')

    response = users_table.get_item(Key={'email': email})
    user = response.get('Item')

    if user and check_password_hash(user['password'], password) and user.get('role') == role:
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
        response = rooms_table.scan()
        rooms = response.get('Items', [])
        return jsonify({'success': True, 'data': rooms})

    elif request.method == 'POST':
        data = request.json

        # Check existing roomNumber
        # Note: In DynamoDB scanning for a specific non-key attribute is inefficient,
        # but for small rooms catalog it works. Alternatively, use Secondary Index.
        response = rooms_table.scan()
        for room in response.get('Items', []):
            if room.get('roomNumber') == str(data.get('roomNumber')):
                return jsonify({'success': False, 'message': 'Room already exists'}), 400

        room_id = uuid.uuid4().hex

        room_data = {
            'roomId': room_id,
            'roomNumber': str(data.get('roomNumber')),
            'type': data.get('type'),
            'price': int(data.get('price', 0)),
            'isAvailable': data.get('isAvailable', True),
            'description': data.get('description', ''),
            'maxOccupancy': int(data.get('maxOccupancy', 2))
        }
        
        rooms_table.put_item(Item=room_data)
        return jsonify({'success': True, 'message': 'Room added'})


@app.route('/api/rooms/<room_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_room(room_id):
    response = rooms_table.get_item(Key={'roomId': room_id})
    room = response.get('Item')

    if not room:
        return jsonify({'success': False, 'message': 'Room not found'}), 404

    if request.method == 'GET':
        return jsonify({'success': True, 'data': room})

    elif request.method == 'PUT':
        data = request.json
        price = data.get('price')
        is_available = data.get('isAvailable')
        desc = data.get('description')
        
        update_expr = []
        expr_attr_values = {}
        
        if price is not None:
            update_expr.append("price = :p")
            expr_attr_values[':p'] = int(price)
        if is_available is not None:
            update_expr.append("isAvailable = :a")
            expr_attr_values[':a'] = is_available
        if desc is not None:
            update_expr.append("description = :d")
            expr_attr_values[':d'] = desc

        if update_expr:
            rooms_table.update_item(
                Key={'roomId': room_id},
                UpdateExpression="SET " + ", ".join(update_expr),
                ExpressionAttributeValues=expr_attr_values
            )
            
        return jsonify({'success': True, 'message': 'Room updated'})

    elif request.method == 'DELETE':
        rooms_table.delete_item(Key={'roomId': room_id})
        return jsonify({'success': True, 'message': 'Room deleted'})


# ------------------ BOOKINGS ------------------

@app.route('/api/bookings', methods=['GET', 'POST'])
def handle_bookings():
    if request.method == 'POST':
        data = request.json

        room_id = data.get('roomId')
        response = rooms_table.get_item(Key={'roomId': room_id})
        room = response.get('Item')

        if not room or not room.get('isAvailable'):
            return jsonify({'success': False, 'message': 'Room unavailable'}), 400

        from_date = datetime.strptime(data.get('fromDate'), '%Y-%m-%d')
        to_date = datetime.strptime(data.get('toDate'), '%Y-%m-%d')

        days = max((to_date - from_date).days, 1)
        total_price = int(room.get('price')) * days

        booking_id = uuid.uuid4().hex

        booking = {
            'bookingId': booking_id,
            'roomId': room_id,
            'roomNumber': room.get('roomNumber'),
            'userName': data.get('userName'),
            'userEmail': data.get('userEmail'),
            'fromDate': data.get('fromDate'),
            'toDate': data.get('toDate'),
            'totalPrice': total_price,
            'status': 'confirmed',
            'createdAt': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }

        bookings_table.put_item(Item=booking)
        
        # update room availability
        rooms_table.update_item(
            Key={'roomId': room_id},
            UpdateExpression="SET isAvailable = :a",
            ExpressionAttributeValues={':a': False}
        )

        return jsonify({'success': True, 'message': 'Booking confirmed', 'data': booking})

    elif request.method == 'GET':
        response = bookings_table.scan()
        bookings = response.get('Items', [])
        return jsonify({'success': True, 'data': bookings})


@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def cancel_booking(booking_id):
    response = bookings_table.get_item(Key={'bookingId': booking_id})
    booking = response.get('Item')

    if not booking:
        return jsonify({'success': False, 'message': 'Booking not found'}), 404

    # make room available again
    rooms_table.update_item(
        Key={'roomId': booking.get('roomId')},
        UpdateExpression="SET isAvailable = :a",
        ExpressionAttributeValues={':a': True}
    )
    
    bookings_table.update_item(
        Key={'bookingId': booking_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={':s': 'cancelled'}
    )

    return jsonify({'success': True, 'message': 'Booking cancelled'})


# ------------------ RUN ------------------

if __name__ == '__main__':
    print("Flask running on EC2 Configuration with AWS bindings on http://0.0.0.0:5000")
    # For EC2 we typically bind to 0.0.0.0 allowing outside requests to reach the host
    app.run(host='0.0.0.0', port=5000, debug=True)