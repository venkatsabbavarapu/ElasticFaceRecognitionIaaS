import boto3
import redis
import json

# Configuration

redis_host = 'localhost'
redis_port = 6379
redis_db = 0

# Initialize SQS client
sqs = boto3.client('sqs', 'us-east-1')

response_queue = '1222291070-resp-queue'
response_queue_url = sqs.get_queue_url(QueueName=response_queue)['QueueUrl']

# Initialize Redis client
r = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)

def poll_sqs_and_store_in_redis():
    while True:
        # Poll SQS queue
        response = sqs.receive_message(
            QueueUrl=response_queue_url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,  # Enable long polling
            MessageAttributeNames=['All']
        )

        if 'Messages' in response:
            for message in response['Messages']:
                # Extract message
                body = message['Body']
                receipt_handle = message['ReceiptHandle']
                message_attributes = message.get('MessageAttributes', {})
                correlation_id = message_attributes.get('CorrelationId', {}).get('StringValue')

                if correlation_id:
                    # Store message in Redis using correlation_id as the key
                    r.set(correlation_id, body)

                    # Delete the message from the SQS queue to prevent reprocessing
                    sqs.delete_message(
                        QueueUrl=response_queue_url,
                        ReceiptHandle=receipt_handle
                    )
                    print(f"Stored message with CorrelationId: {correlation_id} in Redis and deleted from SQS.")
                else:
                    print("Message does not have a CorrelationId.")

if __name__ == '__main__':
    print("Starting to poll SQS and store messages in Redis...")
    poll_sqs_and_store_in_redis()
