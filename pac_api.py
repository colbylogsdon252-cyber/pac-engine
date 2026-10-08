from fastapi import FastAPI
from fastapi.responses import JSONResponse
import uvicorn
import os

from pac_key_management import load_keyring_from_environment

from pac_contract_validator import validate_canonical

def validate_startup_configuration(environ=None):
    env = os.environ if environ is None else environ
    if env.get("PAC_DEPLOYMENT_MODE") == "production":
        return load_keyring_from_environment(env)
    if env.get("PAC_DEPLOYMENT_MODE") not in ("development", "test"):
        raise RuntimeError("PAC_DEPLOYMENT_MODE must explicitly select production, development, or test")
    return None


app = FastAPI(
    title="PAC API v1",
    version="1.0.0"
)


@app.on_event("startup")
def validate_startup():
    validate_startup_configuration()


def map_error_classification_to_http_status(result: dict) -> int:
    """
    API transport adapter only.
    Does not change canonical PAC validation output.
    """
    classifications = result.get("error_classification", []) or []

    codes = {
        item.get("code")
        for item in classifications
        if isinstance(item, dict)
    }

    categories = {
        item.get("category")
        for item in classifications
        if isinstance(item, dict)
    }

    if "halt" in codes or "halt" in categories:
        return 409

    if "reject" in codes or "reject" in categories:
        return 422

    if "state_transition" in categories:
        return 409

    if "payload_type" in categories:
        return 400

    if "validation" in categories:
        return 422

    return 400



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
            status_code=map_error_classification_to_http_status(result),
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
