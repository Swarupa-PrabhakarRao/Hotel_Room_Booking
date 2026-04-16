# Grand Azure Hotel & Resort — AWS Cloud Migration

This repository contains the full-stack code for the Grand Azure Hotel system, now migrated to AWS.

## Architecture
- **Hosting:** AWS EC2 (running Gunicorn/Flask)
- **Database:** AWS DynamoDB (Serverless NoSQL)
- **Communications:** AWS SNS (SMS OTP Verification)
- **Security:** AWS IAM Roles (Credential-less authentication)

## AWS Setup Requirements

### 1. IAM Role (EC2 Instance Profile)
Create an IAM Role and attach it to your EC2 instance with the following managed policies:
- `AmazonDynamoDBFullAccess`
- `AmazonSNSFullAccess`

*Note: In production, use more restrictive policies.*

### 2. DynamoDB Tables
Create the following three tables in the `us-east-1` region:
- **Users**: Partition Key: `email` (String)
- **Rooms**: Partition Key: `roomId` (String)
- **Bookings**: Partition Key: `bookingId` (String)

### 3. SNS Sandbox
If your AWS account is new, SNS starts in a **Sandbox mode**. 
- You must **manually verify** your destination phone numbers in the AWS SNS Console before the system can send SMS OTPs to them.
- Alternatively, request production access from AWS support to send to any number.

## Running Locally (with AWS Credentials)
If running locally, ensure your environment has `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` configured in your environment or `~/.aws/credentials` file.

1. Navigate to `backend/`
2. Install dependencies: `pip install -r requirements.txt`
3. Run: `python app.py`

## Deployment on EC2
1. Clone the repo to your EC2.
2. Install Python & Pip.
3. Install requirements.
4. Run using Gunicorn: `gunicorn --bind 0.0.0.0:5000 app:app`