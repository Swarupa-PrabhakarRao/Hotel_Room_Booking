from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
import uuid
import boto3
from boto3.dynamodb.conditions import Key, Attr
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

# AWS Configuration
# boto3 automatically uses ~/.aws/credentials, or IAM Role permissions if on an EC2 instance
aws_region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
dynamodb = boto3.resource('dynamodb', region_name=aws_region)
sns_client = boto3.client('sns', region_name=aws_region)
SNS_TOPIC_ARN = os.getenv('SNS_TOPIC_ARN', '')

# DynamoDB Tables (You must create these explicitly in the AWS Console)
try:
    users_table = dynamodb.Table('GrandAzure_Users')
    rooms_table = dynamodb.Table('GrandAzure_Rooms')
    bookings_table = dynamodb.Table('GrandAzure_Bookings')
except Exception as e:
    pass

# --- ROUTES ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    
    if not all([name, email, password]):
        return jsonify({'success': False, 'message': 'Missing required fields'}), 400
        
    response = users_table.get_item(Key={'email': email})
    if 'Item' in response:
        return jsonify({'success': False, 'message': 'Email already registered'}), 400
        
    user_doc = {
        'email': email, # Partition key
        'name': name,
        'password_hash': generate_password_hash(password),
        'role': 'user'
    }
    users_table.put_item(Item=user_doc)
    return jsonify({'success': True, 'message': 'User registered successfully'})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    
    response = users_table.get_item(Key={'email': email})
    user = response.get('Item')
    
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
        response = rooms_table.scan()
        rooms = response.get('Items', [])
        # convert Decimal to float/int for JSON serialization
        for r in rooms:
            if 'price' in r: r['price'] = float(r['price'])
        # Sort rooms sequentially
        try:
            rooms = sorted(rooms, key=lambda x: int(x.get('roomNumber', 0)))
        except:
            pass
        return jsonify({'success': True, 'data': rooms})
        
    elif request.method == 'POST':
        data = request.json
        # Check if roomNumber exists
        existing = rooms_table.scan(FilterExpression=Attr('roomNumber').eq(data.get('roomNumber'))).get('Items', [])
        if existing:
            return jsonify({'success': False, 'message': 'Room number already exists'}), 400
            
        new_room = {
            'roomId': uuid.uuid4().hex, # Partition key
            'roomNumber': data.get('roomNumber'),
            'type': data.get('type'),
            'price': int(data.get('price', 0)),
            'isAvailable': data.get('isAvailable', True),
            'description': data.get('description', ''),
            'maxOccupancy': data.get('maxOccupancy', 2)
        }
        rooms_table.put_item(Item=new_room)
        return jsonify({'success': True, 'message': 'Room added'})

@app.route('/api/rooms/<room_id>', methods=['GET', 'PUT', 'DELETE'])
def manage_room(room_id):
    if request.method == 'GET':
        resp = rooms_table.get_item(Key={'roomId': room_id})
        if 'Item' in resp:
            room = resp['Item']
            if 'price' in room: room['price'] = float(room['price'])
            return jsonify({'success': True, 'data': room})
        return jsonify({'success': False, 'message': 'Room not found'}), 404
        
    elif request.method == 'PUT':
        data = request.json
        update_expr = "SET price = :p, isAvailable = :a, description = :d"
        expr_vals = {
            ':p': int(data.get('price', 0)),
            ':a': data.get('isAvailable', True),
            ':d': data.get('description', '')
        }
        rooms_table.update_item(
            Key={'roomId': room_id},
            UpdateExpression=update_expr,
            ExpressionAttributeValues=expr_vals
        )
        return jsonify({'success': True, 'message': 'Room updated'})
        
    elif request.method == 'DELETE':
        rooms_table.delete_item(Key={'roomId': room_id})
        return jsonify({'success': True, 'message': 'Room deleted'})

@app.route('/api/bookings', methods=['GET', 'POST'])
def handle_bookings():
    if request.method == 'POST':
        data = request.json
        room_id = data.get('roomId')
        user_name = data.get('userName')
        user_email = data.get('userEmail')
        from_date_str = data.get('fromDate')
        to_date_str = data.get('toDate')
        
        if not all([room_id, user_name, user_email, from_date_str, to_date_str]):
            return jsonify({'success': False, 'message': 'Missing required fields'}), 400
            
        resp = rooms_table.get_item(Key={'roomId': room_id})
        room = resp.get('Item')
        if not room or not room.get('isAvailable', True):
            return jsonify({'success': False, 'message': 'Room unavailable'}), 400
            
        from_date = datetime.strptime(from_date_str, '%Y-%m-%d')
        to_date = datetime.strptime(to_date_str, '%Y-%m-%d')
        days = (to_date - from_date).days
        if days <= 0: days = 1
        total_price = int(room.get('price', 0)) * days
        
        booking_id = uuid.uuid4().hex
        booking_doc = {
            'bookingId': booking_id, # Partition key
            'roomId': room_id,
            'roomNumber': room.get('roomNumber'),
            'userName': user_name,
            'guestName': user_name,
            'userEmail': user_email,
            'fromDate': from_date_str,
            'toDate': to_date_str,
            'totalPrice': total_price,
            'status': 'confirmed',
            'createdAt': datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        # Mark room as unavailable
        rooms_table.update_item(
            Key={'roomId': room_id},
            UpdateExpression="SET isAvailable = :val",
            ExpressionAttributeValues={':val': False}
        )
        bookings_table.put_item(Item=booking_doc)
        
        # PUBLISH TO AWS SNS MODULE
        if SNS_TOPIC_ARN:
            try:
                sns_client.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Message=f"New Room Booking Processed!\n\nGuest: {user_name} ({user_email})\nSuite: {room.get('roomNumber')}\nCheck In: {from_date_str}\nCheck Out: {to_date_str}\nTotal Cost: ${total_price}"
                )
            except Exception as e:
                print("SNS Error Notification Failed:", e)
        
        booking_doc['totalPrice'] = float(booking_doc['totalPrice'])
        return jsonify({'success': True, 'message': 'Booking confirmed!', 'data': booking_doc})
        
    elif request.method == 'GET':
        email = request.args.get('email')
        if email:
            response = bookings_table.scan(FilterExpression=Attr('userEmail').eq(email))
        else:
            response = bookings_table.scan()
            
        bookings = response.get('Items', [])
        for b in bookings:
            if 'totalPrice' in b: b['totalPrice'] = float(b['totalPrice'])
        return jsonify({'success': True, 'data': bookings})

@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def cancel_booking(booking_id):
    resp = bookings_table.get_item(Key={'bookingId': booking_id})
    booking = resp.get('Item')
    
    if booking:
        # Release the room back into availability
        rooms_table.update_item(
            Key={'roomId': booking['roomId']},
            UpdateExpression="SET isAvailable = :val",
            ExpressionAttributeValues={':val': True}
        )
        
        # Safely update the status using ExpressionAttributeNames since "status" is a reserved keyword in DynamoDB
        bookings_table.update_item(
            Key={'bookingId': booking_id},
            UpdateExpression="SET #s = :val",
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={':val': 'cancelled'}
        )
        
        # OPTIONAL: Send Cancellation SMS via SNS
        if SNS_TOPIC_ARN:
            try:
                sns_client.publish(
                    TopicArn=SNS_TOPIC_ARN,
                    Message=f"Booking Cancellation.\n\nSuite {booking.get('roomNumber')} reservation by {booking.get('userEmail')} was just cancelled."
                )
            except Exception as e:
                pass

        return jsonify({'success': True, 'message': 'Booking cancelled'})
        
    return jsonify({'success': False, 'message': 'Booking not found'}), 404


def seed_db():
    try:
        if not list(rooms_table.scan(Limit=1).get('Items', [])):
            print("Seeding AWS DynamoDB...")
            rooms = [
                {'roomId': uuid.uuid4().hex, 'roomNumber': '101', 'type': 'Single', 'price': 100, 'maxOccupancy': 1, 'isAvailable': True, 'description': ''},
                {'roomId': uuid.uuid4().hex, 'roomNumber': '102', 'type': 'Double', 'price': 150, 'maxOccupancy': 2, 'isAvailable': True, 'description': ''},
                {'roomId': uuid.uuid4().hex, 'roomNumber': '201', 'type': 'Deluxe', 'price': 250, 'maxOccupancy': 3, 'isAvailable': True, 'description': ''},
                {'roomId': uuid.uuid4().hex, 'roomNumber': '301', 'type': 'Suite',  'price': 450, 'maxOccupancy': 4, 'isAvailable': True, 'description': 'Luxury suite with ocean view'}
            ]
            for r in rooms: rooms_table.put_item(Item=r)
            
            users_table.put_item(Item={
                'email': 'admin@grandazure.com',
                'name': 'Admin',
                'password_hash': generate_password_hash('admin123'),
                'role': 'admin'
            })
            print("AWS DynamoDB Database Seeded Successfully!")
    except Exception as e:
        print("Could not seed DB. Make sure tables exist in AWS and credentials are valid! Error:", e)

if __name__ == '__main__':
    seed_db()
    print("🚀 Flask Server linked to AWS DynamoDB & SNS running on port 5000")
    app.run(port=5000, debug=True)
