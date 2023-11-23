import redis
import hashlib
import os
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bs4 import BeautifulSoup

try:
    from readability import Readable
except ImportError:
    from readable_service.readability import Readable

# Initialize Redis client
try:
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=os.getenv("REDIS_PORT", 6379),
        db=int(os.getenv("REDIS_DB", 0)),
    )
    # Check if redis is up
    redis_client.ping()
except Exception as e:
    print("Error connecting to redis: ", e)
    redis_client = None


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
    text: str


@app.post("/convert", response_model=ContentOutput)
def convert(url: URLInput):
    url = url.url
    # check if url is in redis
    unique_key = hashlib.sha256(url.encode()).hexdigest()
    # Check if the data is in cache
    if (
        redis_client is not None
        and (cached_data := redis_client.get(unique_key)) is not None
    ):
        return json.loads(cached_data)

    tmp = Readable(url)
    soup = BeautifulSoup(tmp.article_content, "lxml")
    res = {
        "title": tmp.title,
        "text": soup.get_text(),
    }
    if redis_client is not None:
        redis_client.set(unique_key, json.dumps(res))
    return res


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=50501)
