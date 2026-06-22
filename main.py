import os
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, UUID4
import asyncpg
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="CodeVector Product API")

# Allow UI connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATABASE_URL = os.getenv("DATABASE_URL")
db_pool = None

# --- Pydantic Models ---
class Product(BaseModel):
    id: UUID4
    name: str
    category: str
    price: float
    created_at: datetime
    updated_at: datetime

class PaginatedResponse(BaseModel):
    data: List[Product]
    next_cursor_created_at: Optional[datetime] = None
    next_cursor_id: Optional[UUID4] = None
    has_more: bool

# --- Database Connection Pool ---
@app.on_event("startup")
async def startup():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10)

@app.on_event("shutdown")
async def shutdown():
    await db_pool.close()

# --- The Core Endpoint ---
@app.get("/products", response_model=PaginatedResponse)
async def get_products(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=100, description="Items per page"),
    cursor_created_at: Optional[datetime] = Query(None, description="Timestamp of the last item seen"),
    cursor_id: Optional[UUID4] = Query(None, description="ID of the last item seen")
):
    # Determine if we have a valid cursor
    use_cursor = cursor_created_at is not None and cursor_id is not None
    
    # Base query components
    query_params = []
    where_clauses = []
    param_idx = 1

    # 1. Category Filter
    if category:
        where_clauses.append(f"category = ${param_idx}")
        query_params.append(category)
        param_idx += 1

    # 2. Keyset Pagination (The Cursor)
    # Postgres supports tuple comparison, which is fast and prevents duplicates/skips
    if use_cursor:
        where_clauses.append(f"(created_at, id) < (${param_idx}, ${param_idx + 1})")
        query_params.extend([cursor_created_at, str(cursor_id)])
        param_idx += 2

    # Assemble Query
    where_sql = " AND ".join(where_clauses)
    if where_sql:
        where_sql = f"WHERE {where_sql}"

    # We fetch limit + 1 to easily determine if there is a 'next page'
    sql = f"""
        SELECT id, name, category, price, created_at, updated_at 
        FROM products
        {where_sql}
        ORDER BY created_at DESC, id DESC
        LIMIT ${param_idx}
    """
    query_params.append(limit + 1)

    async with db_pool.acquire() as conn:
        rows = await conn.fetch(sql, *query_params)

    # Process results
    has_more = len(rows) > limit
    results = rows[:limit]  # Trim the extra item if it exists

    next_cursor_created_at = None
    next_cursor_id = None
    if results:
        last_item = results[-1]
        next_cursor_created_at = last_item["created_at"]
        next_cursor_id = last_item["id"]

    # Format output
    products = [dict(row) for row in results]

    return {
        "data": products,
        "next_cursor_created_at": next_cursor_created_at,
        "next_cursor_id": next_cursor_id,
        "has_more": has_more
    }