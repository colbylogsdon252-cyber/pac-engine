from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn

from pac_contract_validator import (
    load_contract,
    validate_payload,
    classify_errors
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
    errors = validate_payload(payload, CONTRACT)

    if errors:
        return JSONResponse(
            status_code=400,
            content={
                "valid": False,
                "errors": errors,
                "error_classification": classify_errors(errors)
            }
        )

    return {
        "valid": True,
        "message": "Payload conforms to PAC contract"
    }


if __name__ == "__main__":
    uvicorn.run(
        "pac_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
