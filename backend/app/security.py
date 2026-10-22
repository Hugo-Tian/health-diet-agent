import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from datetime import timedelta, timezone
from threading import Lock
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from .db import get_db, utcnow
from .models import Session, User

COOKIE = 'diet_session'
SECURE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'
attempts = defaultdict(deque)
rate_lock = Lock()

def fail(status, message, code='invalid_request'):
    raise HTTPException(status, detail={'code': code, 'message': message})

def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'{salt}${digest}'

def check_password(password, stored):
    return hmac.compare_digest(hash_password(password, stored.split('$')[0]), stored)

def throttle(request):
    key = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    with rate_lock:
        for stale in list(attempts):
            if not attempts[stale] or now - attempts[stale][-1] > 300: del attempts[stale]
        queue = attempts[key]
        while queue and now - queue[0] > 300: queue.popleft()
        if len(queue) >= 20: fail(429, '尝试过于频繁，请五分钟后重试', 'rate_limited')
        queue.append(now)

def new_session(db, user, response):
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    db.add(Session(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id, csrf=csrf, expires_at=utcnow()+timedelta(days=7)))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=SECURE, samesite='strict', max_age=604800, path='/')
    return csrf

def auth(request: Request, db=Depends(get_db)):
    token = request.cookies.get(COOKIE, '')
    session = db.get(Session, hashlib.sha256(token.encode()).hexdigest())
    if not session or session.expires_at.replace(tzinfo=timezone.utc) < utcnow():
        fail(401, '请先登录', 'unauthorized')
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if not hmac.compare_digest(request.headers.get('X-CSRF-Token', ''), session.csrf):
            fail(403, '会话校验失败，请刷新后重试', 'csrf')
    user = db.get(User, session.user_id)
    if not user: fail(401, '会话已失效', 'unauthorized')
    request.state.session = session
    return user
