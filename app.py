from fastapi import FastAPI, Header, Response, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional
import uuid
import time
import base64

app = FastAPI()

# -----------------------------
# Root Endpoint
# -----------------------------
@app.get("/")
def root():
    return {"status": "ok", "service": "orders-api"}

# -----------------------------
# Enable CORS
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Assignment Values
# -----------------------------
TOTAL_ORDERS = 54
RATE_LIMIT = 15
WINDOW_SECONDS = 10

# -----------------------------
# In-memory Stores
# -----------------------------
idempotency_store = {}
client_requests = {}

orders = [
    {
        "id": i,
        "item": f"Product {i}"
    }
    for i in range(1, TOTAL_ORDERS + 1)
]

# -----------------------------
# Request Model
# -----------------------------
class OrderRequest(BaseModel):
    item: Optional[str] = "Sample Item"

# -----------------------------
# Cursor Helpers
# -----------------------------
def encode_cursor(index: int) -> str:
    return base64.urlsafe_b64encode(str(index).encode()).decode()

def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception:
        return 0

# -----------------------------
# Rate Limiter
# -----------------------------
def check_rate_limit(client_id: str):

    now = time.time()

    timestamps = client_requests.get(client_id, [])

    timestamps = [
        t for t in timestamps
        if now - t < WINDOW_SECONDS
    ]

    if len(timestamps) >= RATE_LIMIT:

        retry_after = max(
            1,
            int(WINDOW_SECONDS - (now - timestamps[0])) + 1
        )

        return JSONResponse(
            status_code=429,
            content={
                "detail": "Rate limit exceeded"
            },
            headers={
                "Retry-After": str(retry_after)
            }
        )

    timestamps.append(now)

    client_requests[client_id] = timestamps

    return None

# -----------------------------
# POST /orders
# -----------------------------
@app.post("/orders")
def create_order(
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    client_id: str = Header("default", alias="X-Client-Id"),
    order: Optional[OrderRequest] = Body(default=None)
):

    rate_limit = check_rate_limit(client_id)

    if rate_limit:
        return rate_limit

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    response.status_code = 201

    item = "Sample Item"

    if order and order.item:
        item = order.item

    new_order = {
        "id": str(uuid.uuid4()),
        "item": item
    }

    idempotency_store[idempotency_key] = new_order

    return new_order

# -----------------------------
# GET /orders
# -----------------------------
@app.get("/orders")
def get_orders(
    limit: int = 10,
    cursor: Optional[str] = None,
    client_id: str = Header("default", alias="X-Client-Id")
):

    rate_limit = check_rate_limit(client_id)

    if rate_limit:
        return rate_limit

    if limit < 1:
        limit = 1

    start = 0

    if cursor:
        start = decode_cursor(cursor)

    end = min(start + limit, TOTAL_ORDERS)

    items = orders[start:end]

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }
