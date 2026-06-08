import uvicorn
from fastapi import Depends, FastAPI, status
from summary_generator.routers import auth
from summary_generator.routers.auth import get_current_user
from typing import Annotated

app = FastAPI()
user_dependency = Annotated[dict, Depends(get_current_user)]

app.include_router(auth.router)


@app.get("/health", status_code=status.HTTP_200_OK)
async def health():
    return {"status": "I am Healthy!"}


# @app.get("/me", status_code=status.HTTP_200_OK)
# async def get_me(current: user_dependency):
#     return current


def start():
    uvicorn.run("summary_generator.main:app", host="0.0.0.0", port=8000, reload=True)


if __name__ == "__main__":
    start()
