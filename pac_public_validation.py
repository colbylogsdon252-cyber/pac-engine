"""Fail-closed, read-only public validation boundary.

This module does not issue Proof Tokens or authorize execution.
"""
import hmac
import os
import stat

from fastapi import Header, HTTPException

from pac_contract_validator import validate_canonical


def _read_api_key(environ=None):
    env = os.environ if environ is None else environ
    path = env.get("PAC_PUBLIC_API_KEY_FILE")
    if not path:
        return None
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        meta = os.fstat(fd)
        if not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid() or meta.st_mode & 0o077:
            return None
        if meta.st_size < 32 or meta.st_size > 4096:
            return None
        raw = os.read(fd, 4097)
        if len(raw) > 4096:
            return None
        key = raw.decode("utf-8").strip()
        if len(key.encode("utf-8")) < 32:
            return None
        return key
    except (OSError, UnicodeError):
        return None
    finally:
        if fd is not None:
            os.close(fd)


def authenticate(authorization):
    expected = _read_api_key()
    if not expected:
        raise HTTPException(status_code=503, detail="Public validation API is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API credentials")
    supplied = authorization[7:]
    if not hmac.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid API credentials")


def register_public_validation(app, status_mapper):
    from fastapi.responses import JSONResponse

    @app.post("/v1/validations", tags=["Public validation"])
    def public_validate(payload: dict, authorization: str | None = Header(default=None)):
        authenticate(authorization)
        result = dict(validate_canonical(payload))
        result.pop("exit_code", None)
        if not result.get("valid", False):
            return JSONResponse(status_code=status_mapper(result), content=result)
        return result

    return public_validate
