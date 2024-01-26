# import asyncio

# from bs4 import BeautifulSoup
# from readability import Readable

import json
import os

# === AWS Dependencies ===
import boto3

sqs = boto3.client('sqs')
in_sqs_url = os.environ['IN_SQS_URL']

sns = boto3.client('sns')
out_sns_topic_arn = os.environ['OUT_SNS_TOPIC_ARN']

# temporary solution
import requests
READER_URL = os.environ['READER_URL']


def handler(event, context):
  if not event: return
  print(event)
  batch_item_failures = []
  for message in event['Records']:
    body = json.loads(message['body'])
    url = json.loads(body['Message'])['url']
    receipt_handle = message['receiptHandle']
    try:
      # reader request
      data = dict(url=url, is_blog=True)
      res = requests.post(READER_URL, json=data)
      cnt = 0
      while ((res.status_code >= 500) or res.json()['text'] == '') and (cnt < 3):
        res = requests.post(READER_URL, json=data)
        cnt += 1

      res_data = res.json()
      if (len(res_data['text'].strip().split()) < 200) or (res.status_code != 200):
        print('Not a blog. Trying to parse as a normal page')
        data['is_blog'] = False
        res = requests.post(READER_URL, json=data)
        cnt = 0
        while ((res.status_code >= 500) or res.json()['text'] == '') and (cnt < 3):
          res = requests.post(READER_URL, json=data)
          cnt += 1
        if res.status_code != 200: raise Exception(f'Couldn\'t parse {url}. Reader error msg: {res.json()["error"]}')

      print(f'Reader response: {res}')
      res_data = res.json()
      print(f'Reader response: {res_data}')
      title = res_data['title'].strip()
      text = res_data['text'].strip()
      ret = {'title': title, 'text': text, 'url': url}

      # send to out_sns
      _ = sns.publish(
        TopicArn=out_sns_topic_arn,
        Message=json.dumps(ret)
      )

      # delete from in_sqs
      sqs.delete_message(QueueUrl=in_sqs_url, ReceiptHandle=receipt_handle)
    except Exception as e:
      print(f'Error: {e}')
      batch_item_failures.append({'itemIdentifier':message['messageId']})  # add the message to batch_item_failures

  # want to do this, but facing some issues with readability playwright on aws lambda
  # get url and is_blog from event
  # url = event['url']
  # is_blog = event['is_blog']

  # tmp = Readable()
  # tmp.run(url)

  # res =  {}
  # res['title'] = tmp.title
  # soup = BeautifulSoup(tmp.article_content, "lxml")
  # res['text'] = soup.get_text() if is_blog else tmp.text

  return {'batchItemFailures': batch_item_failures}


if __name__ == '__main__':
  event = {
    'url': 'https://www.cloudtechsimplified.com/playwright-aws-lambda-python/',
    'is_blog': True
  }
  print(handler(event, None))