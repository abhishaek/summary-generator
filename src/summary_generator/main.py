import uvicorn
from fastapi import FastAPI, status
from summary_generator.routers import api_router

app = FastAPI()

app.include_router(api_router)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health():
    return {"status": "I am Healthy!"}


def start():
    uvicorn.run("summary_generator.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
