import asyncio

from bs4 import BeautifulSoup
from readability import Readable

def handler(event, context):
  # get url and is_blog from event
  url = event['url']
  is_blog = event['is_blog']

  tmp = Readable()

  loop = asyncio.new_event_loop()
  asyncio.set_event_loop(loop)
  loop.run_until_complete(tmp.run(url))

  res =  {}
  res['title'] = tmp.title
  soup = BeautifulSoup(tmp.article_content, "lxml")
  res['text'] = soup.get_text() if is_blog else tmp.text

  return res