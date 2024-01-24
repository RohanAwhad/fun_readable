import redis
import hashlib
import os
import json
import urllib.parse as urlparse

from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

try:
    from readability import Readable
except ImportError:
    from readable_service.readability import Readable

# Initialize Redis client
redis_client = None
try:
    url = os.getenv("REDISCLOUD_URL", None)
    if url is not None:
        url = urlparse.urlparse(url)
        redis_client = redis.Redis(
            host=url.hostname, port=url.port, password=url.password
        )
    else:
        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=os.getenv("REDIS_PORT", 6379),
            db=int(os.getenv("REDIS_DB", 0)),
        )
    if redis_client.ping():
        print("Connected to Redis")
    else:
        raise Exception("Connection to Redis failed")
except Exception as e:
    print("Error connecting to Redis")
    print(e)
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
    is_blog: bool


class ContentOutput(BaseModel):
    title: str
    text: str
    error: Optional[str] = None


@app.post("/convert", response_model=ContentOutput)
async def convert(inp: URLInput, response: Response):
    url = inp.url
    # check if url is in redis
    unique_key = hashlib.sha256(f"{url}{inp.is_blog}".encode()).hexdigest()
    # Check if the data is in cache
    if (
        redis_client is not None
        and (cached_data := redis_client.get(unique_key)) is not None
    ):
        return json.loads(cached_data)

    # If not, run the Readable algorithm
    try:
        tmp = Readable()
        await tmp.run(url)

        # Create response
        res = {}
        res['title'] = tmp.title
        soup = BeautifulSoup(tmp.article_content, "lxml")
        print(tmp.article_content)
        print(soup.get_text())
        res['text'] = soup.get_text() if inp.is_blog else tmp.text

        # Store in cache
        if redis_client is not None: redis_client.set(unique_key, json.dumps(res))
    except Exception as e:
        res = {
            'title': '',
            'text': '',
            "error": str(e)
        }
        response.status_code = 500
    finally:
        return res


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="localhost", port=50501, reload=True)
