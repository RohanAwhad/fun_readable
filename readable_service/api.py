import redis
import hashlib
import os
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from readability import Readable
from pydantic import BaseModel
from bs4 import BeautifulSoup

# Initialize Redis client
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=os.getenv("REDIS_PORT", 6379),
    db=int(os.getenv("REDIS_DB", 0)),
)


app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthcheck")
def healthcheck():
    return "OK"


class URLInput(BaseModel):
    url: str


class ContentOutput(BaseModel):
    title: str
    article_content: str
    html_content: str
    text: str


@app.post("/convert", response_model=ContentOutput)
def convert(url: URLInput):
    url = url.url
    # check if url is in redis
    unique_key = hashlib.sha256(url.encode()).hexdigest()
    # Check if the data is in cache
    if (cached_data := redis_client.get(unique_key)) is not None:
        return json.loads(cached_data)

    tmp = Readable(url)
    soup = BeautifulSoup(tmp.article_content, "lxml")
    res = {
        "title": tmp.title,
        "article_content": str(tmp.article_content),
        "html_content": str(tmp.html_content),
        "text": soup.get_text(),
    }
    redis_client.set(unique_key, json.dumps(res))
    return res


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=50501)
