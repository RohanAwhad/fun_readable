# Create a FastAPI instance
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from readability import Readable

app = FastAPI()
app.add_middleware(CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.get('/healthcheck')
def healthcheck():
    return 'OK'

@app.get('/convert')
def convert(url: str):
    tmp = Readable(url)
    res = {
        'title': tmp.title,
        'article_content': str(tmp.article_content),
        'html_content': str(tmp.html_content)
    }
    return res

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=50501)
