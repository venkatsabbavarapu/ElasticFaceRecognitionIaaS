from flask import Flask, request, make_response
import werkzeug
from PIL import Image
import base64
import io
import boto3
import uuid
import json
import time  # Import the time module

app = Flask(__name__)

# SQS setup
sqs = boto3.client('sqs', region_name='us-east-1')
request_queue = '1222291070-req-queue'
response_queue = '1222291070-resp-queue'
request_queue_url = sqs.get_queue_url(QueueName=request_queue)['QueueUrl']
response_queue_url = sqs.get_queue_url(QueueName=response_queue)['QueueUrl']

@app.route('/', methods=['POST'])
def handle_post():
    if 'inputFile' not in request.files:
        return make_response("No image file provided", 400)

    image_file = request.files['inputFile']
    if image_file.filename == '':
        return make_response("No selected file", 400)

    image_name = werkzeug.utils.secure_filename(image_file.filename).split('.')[0]
    buffered = io.BytesIO()
    image = Image.open(image_file)
    image.save(buffered, format="JPEG")
    image_bytes = buffered.getvalue()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    correlation_id = str(uuid.uuid4())

    message_body = json.dumps({
        'image_name': image_name,
        'image_data': image_base64
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

    # Start the timeout clock
    start_time = time.time()

    # Poll the response queue for the response with a timeout
    while True:
        # Check for timeout (1 minute)
        if time.time() - start_time > 60:  # 60 seconds
            return make_response("Response timeout", 504)

        messages = sqs.receive_message(
            QueueUrl=response_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,  # Long polling
            MessageAttributeNames=['All']
        )

        if 'Messages' in messages:
            for message in messages['Messages']:
                if message['MessageAttributes'].get('CorrelationId', {}).get('StringValue', '') == correlation_id:
                    # Process and return the response
                    processing_result = json.loads(message['Body'])
                    
                    # Delete the message from the queue
                    sqs.delete_message(
                        QueueUrl=response_queue_url,
                        ReceiptHandle=message['ReceiptHandle']
                    )
                    print(type(processing_result))
                    result=f"{processing_result['image_name']}:{processing_result['processing_result']}"
                    response = make_response(result, 200)
                    response.headers['Content-Type'] = 'text/plain'
                    return response
        else:
            # If no messages, wait for 5 seconds before polling again
            time.sleep(5)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
