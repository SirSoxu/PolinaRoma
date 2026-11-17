import os
import sqlite3
from datetime import date
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from telegram_init_data import validate, parse

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_USERS = {1002916037, 6254805457}

def verify_init_data(init_data: str) -> dict:
    """Проверка подписи initData, предотвращение подделки"""
    try:
        validate(init_data, BOT_TOKEN)
        parsed = parse(init_data)
        user_id = parsed["user"]["id"]
        if user_id not in ALLOWED_USERS:
            raise HTTPException(status_code=403, detail="Access denied")
        return {"user_id": user_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

def get_db():
    conn = sqlite3.connect("tasks.db")
    conn.row_factory = sqlite3.Row
    return conn

class TaskCreate(BaseModel):
    init_data: str
    task_type: str  # global / daily
    content: str

class TaskAction(BaseModel):
    init_data: str
    task_id: int

@app.post("/api/tasks/list")
async def list_tasks(payload: dict = Depends(verify_init_data)):
    conn = get_db()
    today = date.today().isoformat()
    rows = conn.execute("""
        SELECT * FROM tasks 
        WHERE task_type = 'global' 
           OR (task_type = 'daily' AND created_date = ?)
        ORDER BY created_date DESC, id DESC
    """, (today,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.post("/api/tasks/create")
async def create_task(payload: TaskCreate):
    user = verify_init_data(payload.init_data)
    if payload.task_type not in ("global", "daily"):
        raise HTTPException(status_code=400, detail="Invalid task type")
    if not payload.content.strip():
        raise HTTPException(status_code=400, detail="Content required")

    conn = get_db()
    conn.execute(
        "INSERT INTO tasks (creator_id, task_type, content, created_date) VALUES (?, ?, ?, ?)",
        (user["user_id"], payload.task_type, payload.content.strip(), date.today().isoformat())
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/api/tasks/toggle")
async def toggle_task(payload: TaskAction):
    verify_init_data(payload.init_data)
    conn = get_db()
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (payload.task_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Task not found")

    new_status = "done" if row["status"] == "pending" else "pending"
    conn.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, payload.task_id))
    conn.commit()
    conn.close()
    return {"ok": True, "status": new_status}