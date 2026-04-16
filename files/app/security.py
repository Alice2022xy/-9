from itsdangerous import URLSafeSerializer, BadSignature
from fastapi import Request, Response
from passlib.context import CryptContext

from app.settings import SESSION_SECRET, SESSION_COOKIE_NAME

# 纯 Python 哈希算法：避免 bcrypt 在 Windows/conda 下的兼容性坑
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

serializer = URLSafeSerializer(SESSION_SECRET, salt="session")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def set_session(response: Response, user_id: int):
    token = serializer.dumps({"user_id": user_id})
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
    )


def clear_session(response: Response):
    response.delete_cookie(SESSION_COOKIE_NAME)


def get_user_id_from_request(request: Request) -> int | None:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    try:
        data = serializer.loads(token)
        return int(data["user_id"])
    except (BadSignature, KeyError, ValueError):
        return None