from fastapi import FastAPI, Query, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
import asyncpg
import os
import json
import datetime
import uuid
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Theatre Archive API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# ХРАНИЛИЩЕ ФАЙЛОВ
# Чтобы перенести в облако — замени только эти три функции
# ========================

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(Path.home() / "theatre/media")))

def save_file(file_bytes: bytes, original_filename: str) -> str:
    ext = Path(original_filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    (MEDIA_ROOT / unique_name).write_bytes(file_bytes)
    return unique_name

def public_url(file_path: str) -> str:
    return f"http://127.0.0.1:8000/media/{file_path}"

def delete_file(file_path: str):
    p = MEDIA_ROOT / file_path
    if p.exists():
        p.unlink()

app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

# ========================
# БД
# ========================

async def get_db():
    return await asyncpg.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )

def convert(obj):
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")

def resp(data):
    return JSONResponse(
        content=json.loads(json.dumps(data, default=convert)),
        media_type="application/json; charset=utf-8"
    )

def date_or_none(s):
    if not s or not s.strip():
        return None
    try:
        from datetime import date
        return date.fromisoformat(s.strip())
    except Exception:
        return None

# ========================
# ПОИСК
# ========================

@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    db = await get_db()
    try:
        query_str = " & ".join(w + ":*" for w in q.split())
        rows = await db.fetch("""
            SELECT entity_type, id, title,
                   ts_rank(search_vector, to_tsquery('russian_arch', $1)) AS rank
            FROM universal_search
            WHERE search_vector @@ to_tsquery('russian_arch', $1)
            ORDER BY rank DESC LIMIT 20
        """, query_str)
        return resp({"query": q, "results": [dict(r) for r in rows]})
    finally:
        await db.close()

# ========================
# ПЕРСОНЫ
# ========================

class PersonIn(BaseModel):
    last_name: str
    first_name: Optional[str] = None
    patronymic: Optional[str] = None
    born: Optional[str] = None
    died: Optional[str] = None
    roles: Optional[List[str]] = []
    bio: Optional[str] = None

@app.get("/persons")
async def list_persons(limit: int = 50, offset: int = 0):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT id, last_name, first_name, patronymic, roles, born FROM persons ORDER BY last_name LIMIT $1 OFFSET $2",
            limit, offset
        )
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/persons/{person_id}")
async def get_person(person_id: int):
    db = await get_db()
    try:
        person = await db.fetchrow("SELECT * FROM persons WHERE id = $1", person_id)
        if not person:
            return resp({"error": "не найдено"})
        productions = await db.fetch("""
            SELECT p.id, p.title, p.season, pp.role_in_production
            FROM productions p
            JOIN production_persons pp ON pp.production_id = p.id
            WHERE pp.person_id = $1
        """, person_id)
        documents = await db.fetch("""
            SELECT d.id, d.title, d.doc_type, d.file_path, d.date_created,
                   d.description, d.author, d.archive_ref
            FROM documents d
            JOIN object_relations r ON r.source_id = d.id
            WHERE r.source_type = 'document' AND r.target_type = 'person' AND r.target_id = $1
            ORDER BY d.doc_type, d.date_created
        """, person_id)
        docs = []
        for d in documents:
            doc = dict(d)
            doc["url"] = public_url(doc["file_path"]) if doc["file_path"] else None
            docs.append(doc)
        return resp({
            "person": dict(person),
            "productions": [dict(r) for r in productions],
            "documents": docs,
        })
    finally:
        await db.close()

@app.post("/persons")
async def create_person(p: PersonIn):
    db = await get_db()
    try:
        row = await db.fetchrow("""
            INSERT INTO persons (last_name, first_name, patronymic, born, died, roles, bio)
            VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id
        """, p.last_name, p.first_name, p.patronymic,
            date_or_none(p.born), date_or_none(p.died), p.roles, p.bio)
        return resp({"id": row["id"], "status": "ok"})
    finally:
        await db.close()

@app.put("/persons/{person_id}")
async def update_person(person_id: int, p: PersonIn):
    db = await get_db()
    try:
        await db.execute("""
            UPDATE persons SET last_name=$1, first_name=$2, patronymic=$3,
            born=$4, died=$5, roles=$6, bio=$7 WHERE id=$8
        """, p.last_name, p.first_name, p.patronymic,
            date_or_none(p.born), date_or_none(p.died), p.roles, p.bio, person_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

@app.delete("/persons/{person_id}")
async def delete_person(person_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM persons WHERE id=$1", person_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

# ========================
# СПЕКТАКЛИ
# ========================

class ProductionIn(BaseModel):
    title: str
    subtitle: Optional[str] = None
    playwright: Optional[str] = None
    genre: Optional[str] = None
    season: Optional[str] = None
    premiere_date: Optional[str] = None
    last_date: Optional[str] = None
    description: Optional[str] = None

@app.get("/productions")
async def list_productions(limit: int = 50, offset: int = 0):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT id, title, season, genre, premiere_date FROM productions ORDER BY premiere_date DESC NULLS LAST LIMIT $1 OFFSET $2",
            limit, offset
        )
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/productions/{production_id}")
async def get_production(production_id: int):
    db = await get_db()
    try:
        production = await db.fetchrow("SELECT * FROM productions WHERE id = $1", production_id)
        if not production:
            return resp({"error": "не найдено"})
        persons = await db.fetch("""
            SELECT p.id, p.last_name, p.first_name, pp.role_in_production
            FROM persons p
            JOIN production_persons pp ON pp.person_id = p.id
            WHERE pp.production_id = $1
        """, production_id)
        documents = await db.fetch("""
            SELECT d.id, d.title, d.doc_type, d.file_path, d.date_created,
                   d.description, d.author, d.archive_ref
            FROM documents d
            JOIN object_relations r ON r.source_id = d.id
            WHERE r.source_type = 'document' AND r.target_type = 'production' AND r.target_id = $1
            ORDER BY d.doc_type, d.date_created
        """, production_id)
        docs = []
        for d in documents:
            doc = dict(d)
            doc["url"] = public_url(doc["file_path"]) if doc["file_path"] else None
            docs.append(doc)
        return resp({
            "production": dict(production),
            "persons": [dict(r) for r in persons],
            "documents": docs,
        })
    finally:
        await db.close()

@app.post("/productions")
async def create_production(p: ProductionIn):
    db = await get_db()
    try:
        row = await db.fetchrow("""
            INSERT INTO productions (title, subtitle, playwright, genre, season, premiere_date, last_date, description)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
        """, p.title, p.subtitle, p.playwright, p.genre, p.season,
            date_or_none(p.premiere_date), date_or_none(p.last_date), p.description)
        return resp({"id": row["id"], "status": "ok"})
    finally:
        await db.close()

@app.put("/productions/{production_id}")
async def update_production(production_id: int, p: ProductionIn):
    db = await get_db()
    try:
        await db.execute("""
            UPDATE productions SET title=$1, subtitle=$2, playwright=$3, genre=$4,
            season=$5, premiere_date=$6, last_date=$7, description=$8 WHERE id=$9
        """, p.title, p.subtitle, p.playwright, p.genre, p.season,
            date_or_none(p.premiere_date), date_or_none(p.last_date), p.description, production_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

@app.delete("/productions/{production_id}")
async def delete_production(production_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM productions WHERE id=$1", production_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

class ProductionPersonIn(BaseModel):
    person_id: int
    role_in_production: Optional[str] = None

@app.post("/productions/{production_id}/persons")
async def add_person_to_production(production_id: int, data: ProductionPersonIn):
    db = await get_db()
    try:
        await db.execute("""
            INSERT INTO production_persons (production_id, person_id, role_in_production)
            VALUES ($1,$2,$3) ON CONFLICT DO NOTHING
        """, production_id, data.person_id, data.role_in_production or "актёр")
        return resp({"status": "ok"})
    finally:
        await db.close()

@app.delete("/productions/{production_id}/persons/{person_id}")
async def remove_person_from_production(production_id: int, person_id: int):
    db = await get_db()
    try:
        await db.execute(
            "DELETE FROM production_persons WHERE production_id=$1 AND person_id=$2",
            production_id, person_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

# ========================
# ДОКУМЕНТЫ
# ========================

DOC_TYPES = ["фотография", "афиша", "программка", "видеозапись", "рецензия", "текст пьесы", "другое"]

@app.get("/doc-types")
async def get_doc_types():
    return resp(DOC_TYPES)

@app.get("/documents")
async def list_documents(limit: int = 100, offset: int = 0):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT id, title, doc_type, date_created, author, file_path, archive_ref FROM documents ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            limit, offset
        )
        result = []
        for r in rows:
            d = dict(r)
            d["url"] = public_url(d["file_path"]) if d["file_path"] else None
            result.append(d)
        return resp(result)
    finally:
        await db.close()

@app.get("/documents/{doc_id}")
async def get_document(doc_id: int):
    db = await get_db()
    try:
        doc = await db.fetchrow("SELECT * FROM documents WHERE id = $1", doc_id)
        if not doc:
            return resp({"error": "не найдено"})
        productions = await db.fetch("""
            SELECT p.id, p.title, p.season FROM productions p
            JOIN object_relations r ON r.target_id = p.id
            WHERE r.source_type='document' AND r.source_id=$1 AND r.target_type='production'
        """, doc_id)
        persons = await db.fetch("""
            SELECT p.id, p.last_name, p.first_name FROM persons p
            JOIN object_relations r ON r.target_id = p.id
            WHERE r.source_type='document' AND r.source_id=$1 AND r.target_type='person'
        """, doc_id)
        d = dict(doc)
        d["url"] = public_url(d["file_path"]) if d["file_path"] else None
        return resp({
            "document": d,
            "productions": [dict(r) for r in productions],
            "persons": [dict(r) for r in persons],
        })
    finally:
        await db.close()

@app.post("/upload/document")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    doc_type: str = Form("другое"),
    description: str = Form(""),
    author: str = Form(""),
    date_created: str = Form(""),
    production_ids: str = Form("[]"),
    person_ids: str = Form("[]"),
):
    file_bytes = await file.read()
    file_path = save_file(file_bytes, file.filename)
    ext = Path(file.filename).suffix.lower()

    prod_ids = json.loads(production_ids)
    pers_ids = json.loads(person_ids)

    db = await get_db()
    try:
        row = await db.fetchrow("""
            INSERT INTO documents (title, doc_type, description, author, date_created, file_path, file_format)
            VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id
        """, title or file.filename, doc_type,
            description or None, author or None,
            date_or_none(date_created), file_path, ext)

        doc_id = row["id"]

        # Присвоить архивный шифр автоматически
        use_date = date_or_none(date_created) or datetime.date.today().isoformat()
        await db.execute("SELECT assign_archive_ref($1, $2, $3::DATE)", doc_id, doc_type, use_date)

        for pid in prod_ids:
            await db.execute("""
                INSERT INTO object_relations (source_type, source_id, target_type, target_id, relation_type)
                VALUES ('document',$1,'production',$2,'относится к') ON CONFLICT DO NOTHING
            """, doc_id, int(pid))

        for pid in pers_ids:
            await db.execute("""
                INSERT INTO object_relations (source_type, source_id, target_type, target_id, relation_type)
                VALUES ('document',$1,'person',$2,'изображает') ON CONFLICT DO NOTHING
            """, doc_id, int(pid))

        # Получить присвоенный шифр
        ref_row = await db.fetchrow("SELECT archive_ref FROM documents WHERE id=$1", doc_id)
        archive_ref = ref_row["archive_ref"] if ref_row else None

        return resp({"id": doc_id, "url": public_url(file_path), "archive_ref": archive_ref, "status": "ok"})
    finally:
        await db.close()

@app.put("/documents/{doc_id}")
async def update_document(
    doc_id: int,
    title: str = Form(""),
    doc_type: str = Form("другое"),
    description: str = Form(""),
    author: str = Form(""),
    date_created: str = Form(""),
    production_ids: str = Form("[]"),
    person_ids: str = Form("[]"),
):
    prod_ids = json.loads(production_ids)
    pers_ids = json.loads(person_ids)

    db = await get_db()
    try:
        await db.execute("""
            UPDATE documents SET title=$1, doc_type=$2, description=$3, author=$4, date_created=$5
            WHERE id=$6
        """, title, doc_type, description or None, author or None,
            date_or_none(date_created), doc_id)

        await db.execute(
            "DELETE FROM object_relations WHERE source_type='document' AND source_id=$1", doc_id)
        for pid in prod_ids:
            await db.execute("""
                INSERT INTO object_relations (source_type, source_id, target_type, target_id, relation_type)
                VALUES ('document',$1,'production',$2,'относится к')
            """, doc_id, int(pid))
        for pid in pers_ids:
            await db.execute("""
                INSERT INTO object_relations (source_type, source_id, target_type, target_id, relation_type)
                VALUES ('document',$1,'person',$2,'изображает')
            """, doc_id, int(pid))

        return resp({"status": "ok"})
    finally:
        await db.close()

@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    db = await get_db()
    try:
        row = await db.fetchrow("SELECT file_path FROM documents WHERE id=$1", doc_id)
        if row and row["file_path"]:
            delete_file(row["file_path"])
        await db.execute("DELETE FROM object_relations WHERE source_type='document' AND source_id=$1", doc_id)
        await db.execute("DELETE FROM archive_units WHERE object_type='document' AND object_id=$1", doc_id)
        await db.execute("DELETE FROM documents WHERE id=$1", doc_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

# ========================
# АРХИВНАЯ СТРУКТУРА
# ========================

@app.get("/archive/funds")
async def list_funds():
    db = await get_db()
    try:
        rows = await db.fetch("SELECT * FROM funds ORDER BY id")
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/archive/funds/{fund_id}/inventories")
async def list_inventories(fund_id: int):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT * FROM inventories WHERE fund_id=$1 ORDER BY number", fund_id)
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/archive/inventories/{inventory_id}/cases")
async def list_cases(inventory_id: int):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT * FROM cases WHERE inventory_id=$1 ORDER BY number", inventory_id)
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/archive/cases/{case_id}/units")
async def list_units(case_id: int):
    db = await get_db()
    try:
        rows = await db.fetch("""
            SELECT au.*, d.title as doc_title, d.doc_type, d.file_path, d.archive_ref
            FROM archive_units au
            LEFT JOIN documents d ON d.id = au.object_id AND au.object_type = 'document'
            WHERE au.case_id = $1
            ORDER BY au.unit_number::INT
        """, case_id)
        result = []
        for r in rows:
            d = dict(r)
            if d.get("file_path"):
                d["url"] = public_url(d["file_path"])
            result.append(d)
        return resp(result)
    finally:
        await db.close()
