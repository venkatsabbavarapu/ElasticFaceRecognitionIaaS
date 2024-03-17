import boto3
import time
import logging

# Configure logging
logging.basicConfig(filename='autoscaling.log', level=logging.INFO, 
                    format='%(asctime)s %(levelname)s: %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

asu_id = '1222291070'  # Replace with your actual ASU ID
request_queue = f'{asu_id}-req-queue'
ami_id = 'ami-033e450ef81a969dc'
key_pair = 'CC_KeyPair'
ec2_resource = boto3.resource('ec2', region_name='us-east-1')
ec2_client = boto3.client('ec2', region_name='us-east-1')
sqs_client = boto3.client('sqs', region_name='us-east-1')

queue_url = sqs_client.get_queue_url(QueueName=request_queue)['QueueUrl']
iam_instance_profile_arn = 'arn:aws:iam::665435622782:instance-profile/CCAppTierRole'
instance_ids = []

def update_instance_ids():
    instances = ec2_client.describe_instances(Filters=[
        {'Name': 'tag:Name', 'Values': ['app-tier-instance-*']},
        {'Name': 'instance-state-name', 'Values': ['running']}
    ])
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            instance_ids.append(instance['InstanceId'])
    logging.info(f'Updated instance IDs: {instance_ids}')

update_instance_ids()

def generate_instance_name():
    next_number = len(instance_ids) + 1
    instance_name = f'app-tier-instance-{next_number}'
    return instance_name

def create_ec2_instance(iam_instance_profile_arn):
    instance_name = generate_instance_name()
    instance = ec2_resource.create_instances(
        ImageId=ami_id,
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        KeyName=key_pair,
        IamInstanceProfile={'Arn': iam_instance_profile_arn},
        TagSpecifications=[
            {'ResourceType': 'instance',
             'Tags': [{'Key': 'Name', 'Value': instance_name}]}
        ]
    )[0]
    logging.info(f'Created EC2 Instance {instance.id} with name {instance_name}')
    instance_ids.append(instance.id)

def terminate_ec2_instance():
    if instance_ids:
        instance_id_to_terminate = instance_ids.pop()
        ec2_resource.Instance(instance_id_to_terminate).terminate()
        logging.info(f'Terminating EC2 Instance {instance_id_to_terminate}')
    else:
        logging.info('No instances to terminate.')

def check_queue_length(queue_url):
    response = sqs_client.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=['ApproximateNumberOfMessages']
    )
    queue_length = int(response['Attributes']['ApproximateNumberOfMessages'])
    logging.info(f'Queue length: {queue_length}')
    return queue_length

def monitor_and_scale():
    empty_queue_checks = 0
    while True:
        queue_length = check_queue_length(queue_url)
        if queue_length==0:
            empty_queue_checks += 1
            if empty_queue_checks >= 2:
                while instance_ids:
                    terminate_ec2_instance()
                empty_queue_checks = 0
        elif queue_length > 20:
            empty_queue_checks = 0
            logging.info('High queue load detected, creating an EC2 instance...')
            while len(instance_ids) < 20:
                create_ec2_instance(iam_instance_profile_arn)
        elif queue_length <= 20:
            empty_queue_checks = 0
            while len(instance_ids) < queue_length:
                create_ec2_instance(iam_instance_profile_arn)
        time.sleep(30)

if __name__ == '__main__':
    monitor_and_scale()
