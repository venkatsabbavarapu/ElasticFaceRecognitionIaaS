#!/usr/bin/env python3

import os
import csv
import sys
import torch
from facenet_pytorch import MTCNN, InceptionResnetV1
from torchvision import datasets
from torch.utils.data import DataLoader
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

mtcnn = MTCNN(image_size=240, margin=0, min_face_size=20) # initializing mtcnn for face detection
resnet = InceptionResnetV1(pretrained='vggface2').eval() # initializing resnet for face img to embeding conversion


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

def face_match(image, data_path): # img_path= location of photo, data_path= location of data.pt
    # getting embedding matrix of the given img
    # img = Image.open(img_path)
    face, prob = mtcnn(image, return_prob=True) # returns cropped face and probability
    emb = resnet(face.unsqueeze(0)).detach() # detech is to make required gradient false

    saved_data = torch.load('data.pt') # loading data.pt file
    embedding_list = saved_data[0] # getting embedding data
    name_list = saved_data[1] # getting list of names
    dist_list = [] # list of matched distances, minimum distance is used to identify the person

    for idx, emb_db in enumerate(embedding_list):
        dist = torch.dist(emb, emb_db).item()
        dist_list.append(dist)

    idx_min = dist_list.index(min(dist_list))
    return (name_list[idx_min], min(dist_list))


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
    result = face_match(image,'data.pt')
    output = result[0].strip()
    
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
