import uvicorn
from fastapi import FastAPI

app = FastAPI()


@app.get("/health")
async def health():
    return {"status": "Ok!"}


def start():
    uvicorn.run("summary_generator.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
