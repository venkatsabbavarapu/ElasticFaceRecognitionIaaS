from flask import Flask, request, make_response
import werkzeug
from PIL import Image
import base64
import io
import boto3
import uuid
import json
import time
import redis
import logging  # Import logging module

app = Flask(__name__)

# Configure logging
logging.basicConfig(filename='web-tier.log', level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s')

# SQS setup
sqs = boto3.client('sqs', region_name='us-east-1')
request_queue = '1222291070-req-queue'
response_queue = '1222291070-resp-queue'
request_queue_url = sqs.get_queue_url(QueueName=request_queue)['QueueUrl']
response_queue_url = sqs.get_queue_url(QueueName=response_queue)['QueueUrl']

# Redis setup
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)  # Connect to local Redis instance

@app.route('/', methods=['POST'])
def handle_post():
    if 'inputFile' not in request.files:
        logging.error("No image file provided")
        return make_response("No image file provided", 400)

    image_file = request.files['inputFile']
    if image_file.filename == '':
        logging.error("No selected file")
        return make_response("No selected file", 400)

    logging.info("Processing file: %s", image_file.filename)
    
    image_name = werkzeug.utils.secure_filename(image_file.filename).split('.')[0]
    
    image_data=image_file.read()
    
    image_base64 = base64.b64encode(image_data).decode('utf-8')
    correlation_id = str(uuid.uuid4())

    message_body = json.dumps({
        'image_name': image_name,
        'image_data': image_base64,
        'correlation_id': correlation_id
    })

    # Send a message to the request queue
    sqs.send_message(
        QueueUrl=request_queue_url,
        MessageBody=message_body,
        MessageAttributes={
            'CorrelationId': {
                'StringValue': correlation_id,
                'DataType': 'String'
            },
            'FileName': {
                'StringValue': image_name,
                'DataType': 'String'
            }
        }
    )
    
    logging.info("Message sent for image %s with correlation ID %s", image_name, correlation_id)

    # Start the timeout clock
    start_time = time.time()

    # Check the Redis store for the response with a timeout
    while True:
        if time.time() - start_time > 300:  # 300 seconds
            logging.warning("Response timeout for correlation ID %s", correlation_id)
            return make_response("Response timeout", 504)

        processing_result = r.get(correlation_id)
        if processing_result:
            processing_result = json.loads(processing_result)
            result = f"{processing_result['image_name']}:{processing_result['processing_result']}"
            response = make_response(result, 200)
            response.headers['Content-Type'] = 'text/plain'
            logging.info("Processing result retrieved for correlation ID %s", correlation_id)
            return response
        else:
            time.sleep(1)  # Sleep briefly to avoid hammering Redis

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8000, threaded=True)
