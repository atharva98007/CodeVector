import os
import uuid
import random
from datetime import datetime, timedelta, timezone
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
TOTAL_RECORDS = 200000
BATCH_SIZE = 10000

CATEGORIES = ["Electronics", "Clothing", "Home & Kitchen", "Books", "Sports", "Toys", "Beauty"]
ADJECTIVES = ["Premium", "Wireless", "Ergonomic", "Portable", "Smart", "Minimalist", "Durable"]
NOUNS = ["Widget", "Device", "Monitor", "Headphones", "Tracker", "Bottle", "Backpack"]

def generate_mock_data(num_records):
    """Generates mock product data entirely in memory."""
    now = datetime.now(timezone.utc)
    data = []
    for _ in range(num_records):
        record_id = str(uuid.uuid4())
        name = f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)}"
        category = random.choice(CATEGORIES)
        price = round(random.uniform(9.99, 999.99), 2)
        
        # Stagger created_at times over the last 365 days
        days_ago = random.uniform(0, 365)
        created_at = now - timedelta(days=days_ago)
        updated_at = created_at
        
        data.append((record_id, name, category, price, created_at, updated_at))
    
    # Sort in memory before insert to slightly optimize Postgres index building
    data.sort(key=lambda x: x[4]) 
    return data

def setup_database():
    """Connects to DB, creates the table, composite indexes, and seeds data."""
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("Creating table and indexes...")
    cur.execute("""
        DROP TABLE IF EXISTS products;
        CREATE TABLE products (
            id UUID PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(100) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL
        );
        -- The crucial composite index for fast cursor pagination + filtering
        CREATE INDEX idx_products_category_created_id ON products (category, created_at DESC, id DESC);
        CREATE INDEX idx_products_created_id ON products (created_at DESC, id DESC);
    """)
    conn.commit()

    print(f"Generating {TOTAL_RECORDS} mock products in memory...")
    records = generate_mock_data(TOTAL_RECORDS)

    print("Bulk inserting records...")
    insert_query = """
        INSERT INTO products (id, name, category, price, created_at, updated_at)
        VALUES %s
    """
    
    for i in range(0, TOTAL_RECORDS, BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        execute_values(cur, insert_query, batch)
        conn.commit()
        print(f"Inserted {i + len(batch)} / {TOTAL_RECORDS}")

    cur.close()
    conn.close()
    print("Database seeding complete!")

if __name__ == "__main__":
    setup_database()