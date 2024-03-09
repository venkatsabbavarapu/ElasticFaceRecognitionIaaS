import boto3
import time


asu_id = '1222291070'  # Replace with your actual ASU ID
request_queue = f'{asu_id}-req-queue'
ami_id='ami-0e1b6db259f90d2a6'
key_pair='CC_KeyPair'
# Initialize the boto3 client and resource
ec2_resource = boto3.resource('ec2', region_name='us-east-1')
ec2_client = boto3.client('ec2', region_name='us-east-1')
sqs_client = boto3.client('sqs', region_name='us-east-1')

# Your SQS queue URL

queue_url = sqs_client.get_queue_url(QueueName=request_queue)['QueueUrl']
# IAM instance profile ARN
iam_instance_profile_arn = 'arn:aws:iam::665435622782:instance-profile/SQSandS3AccessEC2'

# List to keep track of created instance IDs
instance_ids = []

# Function to generate the next instance name based on existing instances
def generate_instance_name():
    # Your logic to generate the instance name...
    next_number = len(instance_ids)+1  # Example starting point
    # Determine the next_number based on your existing instances logic
    instance_name = f'app-tier-instance-{next_number}'
    return instance_name

# Function to create an EC2 instance and attach IAM role
def create_ec2_instance(iam_instance_profile_arn):
    instance_name = generate_instance_name()
    instance = ec2_resource.create_instances(
        ImageId=ami_id,  # Update this to your AMI ID
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',  # Update as per your requirement
        KeyName=key_pair,  # Update this to your key pair
        IamInstanceProfile={'Arn': iam_instance_profile_arn},
        TagSpecifications=[
            {'ResourceType': 'instance',
             'Tags': [{'Key': 'Name', 'Value': instance_name}]}
        ]
    )[0]
    print(f'Created EC2 Instance {instance.id} with name {instance_name}')
    # Add the instance ID to the tracking list
    instance_ids.append(instance.id)

# Function to terminate the most recently created instance
def terminate_ec2_instance():
    if instance_ids:
        # Get the most recent instance ID and attempt to terminate it
        instance_id_to_terminate = instance_ids.pop()
        ec2_resource.Instance(instance_id_to_terminate).terminate()
        print(f'Terminating EC2 Instance {instance_id_to_terminate}')
    else:
        print('No instances to terminate.')

# Function to check the queue length
def check_queue_length(queue_url):
    response = sqs_client.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['ApproximateNumberOfMessages']
    )
    return int(response['Attributes']['ApproximateNumberOfMessages'])

# Main function to monitor and scale
def monitor_and_scale():
    while True:
        queue_length = check_queue_length(queue_url)
        print(f'Queue length: {queue_length}')
        if not queue_length:
            while(instance_ids):
                terminate_ec2_instance()
        elif queue_length > 20:  # Example threshold for scaling up
            print('High queue load detected, creating an EC2 instance...')
            while(len(instance_ids)<20):
                create_ec2_instance(iam_instance_profile_arn)                      
        elif queue_length <= 20:
            while(len(instance_ids)<queue_length):
                create_ec2_instance(iam_instance_profile_arn)
                
        time.sleep(30)  # Adjust as necessary

if __name__ == '__main__':
    monitor_and_scale()
