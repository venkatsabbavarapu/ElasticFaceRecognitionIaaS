import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import time

asu_id = '1222291070'
request_queue = f'{asu_id}-req-queue'
asg_name = 'app-tier-asg'

# Constants to define your SQS queue and ASG names
SCALE_OUT_THRESHOLD = 50  # Threshold to increase the number of instances
SCALE_IN_THRESHOLD = 10   # Threshold to decrease the number of instances
MAX_INSTANCES = 20        # Maximum number of instances in the ASG
INTERVAL = 5              # Run every 5 seconds

def get_queue_length(sqs_client, queue_name):
    try:
        # Get the SQS queue URL
        queue_url = sqs_client.get_queue_url(QueueName=queue_name)['QueueUrl']
        # Get the number of messages in the queue
        attributes = sqs_client.get_queue_attributes(
            QueueUrl=queue_url, AttributeNames=['ApproximateNumberOfMessages'])
        return int(attributes['Attributes']['ApproximateNumberOfMessages'])
    except ClientError as e:
        print(f"Error getting queue length: {e}")
        return None

def scale_out(asg_client, asg_name, desired_capacity):
    try:
        asg_client.set_desired_capacity(
            AutoScalingGroupName=asg_name, DesiredCapacity=desired_capacity, HonorCooldown=True)
        print(f"Scaling out: Set desired capacity to {desired_capacity}")
    except ClientError as e:
        print(f"Error scaling out: {e}")

def scale_in(asg_client, asg_name, desired_capacity):
    try:
        asg_client.set_desired_capacity(
            AutoScalingGroupName=asg_name, DesiredCapacity=desired_capacity, HonorCooldown=True)
        print(f"Scaling in: Set desired capacity to {desired_capacity}")
    except ClientError as e:
        print(f"Error scaling in: {e}")

def main_loop():
    # Initialize boto3 clients
    sqs_client = boto3.client('sqs', region_name='us-east-1')
    asg_client = boto3.client('autoscaling', region_name='us-east-1')

    while True:
        try:
            # Get current queue length
            queue_length = get_queue_length(sqs_client, request_queue)
            if queue_length is not None:
                print(f"Current queue length: {queue_length}")

                # Check scaling policies
                if queue_length > SCALE_OUT_THRESHOLD:
                    # Scale out
                    desired_capacity = min(MAX_INSTANCES, queue_length // SCALE_OUT_THRESHOLD)  # Calculate desired capacity
                    scale_out(asg_client, asg_name, desired_capacity)
                elif queue_length <= SCALE_IN_THRESHOLD:
                    # Scale in
                    desired_capacity = max(0, queue_length // SCALE_IN_THRESHOLD)  # Calculate desired capacity, ensure at least 1
                    scale_in(asg_client, asg_name, desired_capacity)

        except NoCredentialsError:
            print("Error: AWS credentials not found.")

        time.sleep(INTERVAL)  # Wait for 5 seconds before the next run

if __name__ == "__main__":
    main_loop()
