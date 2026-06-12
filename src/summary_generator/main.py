import uvicorn
from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from summary_generator.limiter import limiter
from summary_generator.routers import api_router
from summary_generator.logging_config import setup_logging

setup_logging()
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],            
    allow_credentials=True,           
    allow_methods=["*"],              
    allow_headers=["*"],              
)

@app.get("/", status_code=status.HTTP_200_OK)
def read_root():
    return {"message": "CORS-enabled response"}


@app.get("/health", status_code=status.HTTP_200_OK)
async def health():
    return {"status": "I am Healthy!"}


def start():
    uvicorn.run("summary_generator.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
