#!/usr/bin/env python3


import logging
import boto3
import json
import subprocess
import time
from PIL import Image
import base64
from io import BytesIO

# Setup logging
logging.basicConfig(filename='process.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# AWS Setup
sqs = boto3.client('sqs', region_name='us-east-1')
s3 = boto3.client('s3')
asu_id = '1222291070'  # Replace with your actual ASU ID
input_bucket = f'{asu_id}-in-bucket'
output_bucket = f'{asu_id}-out-bucket'
request_queue = f'{asu_id}-req-queue'
response_queue = f'{asu_id}-resp-queue'

request_queue_url = sqs.get_queue_url(QueueName=request_queue)['QueueUrl']
response_queue_url = sqs.get_queue_url(QueueName=response_queue)['QueueUrl']

def process_message(message):
    message_body = json.loads(message['Body'])
    image_name = message_body['image_name']
    image_data = message_body['image_data']
    receipt_handle = message['ReceiptHandle']
    correlation_id = message['MessageAttributes']['CorrelationId']['StringValue']

    logging.info(f"Processing image: {image_name} with Correlation ID: {correlation_id}")

    # Decode the Base64 image data
    decoded_image_data = base64.b64decode(image_data)
    image = Image.open(BytesIO(decoded_image_data))
    image_path = f"/tmp/{image_name}.jpg"
    image.save(image_path, 'JPEG')
    
    # Upload the image to the S3 input bucket
    s3.upload_file(image_path, input_bucket, f"{image_name}.jpg")
    logging.info(f"Image uploaded to S3 input bucket: {input_bucket}/{image_name}.jpg")

    # Run the recognition script and capture the output
    result = subprocess.run(['python3', 'face_recognition.py', image_path],cwd='./model/', capture_output=True, text=True)
    output = result.stdout.strip()
    logging.info(result)
    logging.info(f"Recognition result: {output}")

    # Save the result to the S3 output bucket
    s3.put_object(Bucket=output_bucket, Key=f"{image_name}", Body=output)
    logging.info(f"Result uploaded to S3 output bucket: {output_bucket}/{image_name}")

    # Send the processing result to the response queue with Correlation ID
    sqs.send_message(
        QueueUrl=response_queue_url,
        MessageBody=json.dumps({'image_name': image_name, 'processing_result': output}),
        MessageAttributes={
            'CorrelationId': {
                'StringValue': correlation_id,
                'DataType': 'String'
            }
        }
    )
    logging.info("Result sent to response queue")

    # Delete the processed message from the request queue
    sqs.delete_message(QueueUrl=request_queue_url, ReceiptHandle=receipt_handle)
    logging.info("Message deleted from request queue")

# Main loop to continuously monitor for messages
while True:
    try:
        response = sqs.receive_message(
            QueueUrl=request_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,  # Enable long polling
            MessageAttributeNames=['All']
        )

        messages = response.get('Messages', [])
        if messages:
            for message in messages:
                process_message(message)
        else:
            logging.info("No messages in queue. Waiting...")
            time.sleep(5)  # Wait before polling again to avoid excessive resource usage
    except Exception as e:
        logging.error(f"Error processing message: {str(e)}")
        time.sleep(10)  # Wait a bit longer if there's an error before trying again
