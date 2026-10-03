from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from pac_contract_validator import (
    load_contract,
    validate_canonical
)

app = FastAPI(
    title="PAC API v1",
    version="1.0.0"
)

CONTRACT = load_contract()


@app.get("/")
def root():
    return {
        "system": "PAC API v1",
        "status": "online",
        "validation_engine": "active"
    }


@app.post("/validate")
def validate(payload: dict):
    result = validate_canonical(payload)

    response_body = dict(result)
    response_body.pop("exit_code", None)

    if not result.get("valid", False):
        return JSONResponse(
            status_code=400,
            content=response_body
        )

    return response_body


if __name__ == "__main__":
    uvicorn.run(
        "pac_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
