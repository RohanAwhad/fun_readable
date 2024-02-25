# import asyncio

# from bs4 import BeautifulSoup
# from readability import Readable

import json
import os
from datetime import datetime, timezone

# === AWS Dependencies ===
import boto3

sqs = boto3.client("sqs")
in_sqs_url = os.environ["IN_SQS_URL"]

sns = boto3.client("sns")
out_sns_topic_arn = os.environ["OUT_SNS_TOPIC_ARN"]

dynamodb = boto3.resource("dynamodb")

# temporary solution
import requests

READER_URL = os.environ["READER_URL"]
READER_HTML_URL = os.environ["READER_HTML_URL"]


def handler(event, context):
    if not event:
        return
    print(event)
    batch_item_failures = []
    for message in event["Records"]:
        body = json.loads(message["body"])
        msg = json.loads(body["Message"])
        url = msg["url"]
        is_html = msg["is_html"]
        table_name = msg["table_name"]
        receipt_handle = message["receiptHandle"]
        try:
            # reader request
            if is_html:
                # Get HTML from the table's "pageHTML" column
                table = dynamodb.Table(table_name)
                response = table.get_item(Key={"url": url})
                page_html = response["Item"]["pageHTML"]
                data = dict(html=page_html)
                res = requests.post(READER_HTML_URL, json=data)
            else:
                data = dict(url=url, is_blog=True)
                res = requests.post(READER_URL, json=data)

            cnt = 0
            while ((res.status_code >= 500) or res.json()["text"] == "") and (cnt < 3):
                if is_html:
                    res = requests.post(READER_HTML_URL, json=data)
                else:
                    res = requests.post(READER_URL, json=data)
                cnt += 1

            res_data = res.json()
            if (len(res_data["text"].strip().split()) < 200) or (res.status_code != 200):
                print("Not a blog. Trying to parse as a normal page")
                data["is_blog"] = False
                res = requests.post(READER_URL, json=data)
                cnt = 0
                while ((res.status_code >= 500) or res.json()["text"] == "") and (cnt < 3):
                    res = requests.post(READER_URL, json=data)
                    cnt += 1
                if res.status_code != 200:
                    raise Exception(f'Couldn\'t parse {url}. Reader error msg: {res.json()["error"]}')

            print(f"Reader response: {res}")
            res_data = res.json()
            print(f"Reader response: {res_data}")
            title = res_data["title"].strip()
            text = res_data["text"].strip()

            # save to dynamodb
            table = dynamodb.Table(table_name)
            updates = {
                "page_title": title,
                "page_text": text,
                "updated_on": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            }
            update_expression = [f"{x}=:{x}" for x in updates.keys()]  # ['title=:title', 'text=:text', ...]
            update_expression = "SET " + ", ".join(update_expression)  # 'SET title=:title, text=:text, ...'
            exp_attr_values = {f":{k}": v for k, v in updates.items()}  # {':title': '...', ':text': '...', ...}
            table.update_item(
                Key=dict(url=data["url"]), UpdateExpression=update_expression, ExpressionAttributeValues=exp_attr_values
            )

            # send to out_sns
            ret = {"url": url, "table_name": table_name}
            _ = sns.publish(TopicArn=out_sns_topic_arn, Message=json.dumps(ret))

            # delete from in_sqs
            sqs.delete_message(QueueUrl=in_sqs_url, ReceiptHandle=receipt_handle)
        except Exception as e:
            print(f"Error: {e}")
            batch_item_failures.append(
                {"itemIdentifier": message["messageId"]}
            )  # add the message to batch_item_failures

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

    return {"batchItemFailures": batch_item_failures}


if __name__ == "__main__":
    event = {"url": "https://www.cloudtechsimplified.com/playwright-aws-lambda-python/", "is_blog": True}
    print(handler(event, None))
