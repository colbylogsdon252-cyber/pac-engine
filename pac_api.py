from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List
from fastapi.responses import JSONResponse
from pac_engine_v1_interface import evaluate_payload


app = FastAPI(
    title="PAC Validation API",
    version="1.0.0",
    description="Production-grade PAC validation and enforcement API."
)


def status_for_decision(decision: str) -> int:
    if decision == "APPROVE":
        return 200
    if decision == "REJECT":
        return 422
    if decision == "HALT":
        return 400
    return 500


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "pac-validation-api",
        "version": "1.0.0"
    }


@app.post("/validate")
async def validate(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "decision": "HALT",
                "proof_complete": False,
                "required_threshold": None,
                "reasons": ["Invalid JSON input"],
                "failed_constraints": [],
                "missing_stages": [],
                "proof_state": {},
                "error": str(exc)
            }
        )

    try:
        result = evaluate_payload(payload)
    except Exception as exc:
        return JSONResponse(
            status_code=500,
            content={
                "decision": "HALT",
                "proof_complete": False,
                "required_threshold": None,
                "reasons": ["PAC API execution error"],
                "failed_constraints": [],
                "missing_stages": [],
                "proof_state": {},
                "error": str(exc)
            }
        )

    return JSONResponse(
        status_code=status_for_decision(result.get("decision")),
        content=result
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("pac_api:app", host="0.0.0.0", port=8000, reload=True)