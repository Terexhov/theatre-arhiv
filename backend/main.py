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

app = FastAPI(
    root_path="/api",
    title="Личный архив Эдуарда Боякова",
    description="API архива — управление персонами, спектаклями и документами",
    version="1.0.0",
    openapi_tags=[
        {"name": "search", "description": "Полнотекстовый поиск"},
        {"name": "archive", "description": "Архивная структура — фонды, описи, дела"},
        {"name": "persons", "description": "Персоналии"},
        {"name": "productions", "description": "Спектакли и проекты"},
        {"name": "documents", "description": "Документы — фото, видео, тексты и др."},
    ]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# ХРАНИЛИЩЕ ФАЙЛОВ
# Замени эти три функции для переноса в облако
# ========================

MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", str(Path.home() / "theatre/media")))

def save_file(file_bytes: bytes, original_filename: str) -> str:
    ext = Path(original_filename).suffix.lower()
    unique_name = f"{uuid.uuid4().hex}{ext}"
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    (MEDIA_ROOT / unique_name).write_bytes(file_bytes)
    return unique_name

def public_url(file_path: str) -> str:
    base = os.getenv("MEDIA_BASE_URL", "http://178.253.38.120/media")
    return f"{base}/{file_path}"

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
    if isinstance(obj, bool):
        return obj
    raise TypeError(f"Not serializable: {type(obj)}")

def resp(data):
    return JSONResponse(
        content=json.loads(json.dumps(data, default=convert)),
        media_type="application/json; charset=utf-8"
    )

def date_or_none(s):
    if not s or not str(s).strip():
        return None
    try:
        return datetime.date.fromisoformat(str(s).strip())
    except Exception:
        return None

# ========================
# ПОИСК
# ========================

@app.get("/search", tags=["search"], summary="Полнотекстовый поиск по всем сущностям")
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
# АРХИВНАЯ СТРУКТУРА
# ========================

@app.get("/archive/funds", tags=["archive"], summary="Список фондов")
async def list_funds():
    db = await get_db()
    try:
        rows = await db.fetch("SELECT * FROM funds ORDER BY id")
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/archive/inventories", tags=["archive"], summary="Все описи")
async def list_inventories():
    db = await get_db()
    try:
        rows = await db.fetch("""
            SELECT i.*, f.code as fund_code, f.name as fund_name,
                   (SELECT COUNT(*) FROM cases c WHERE c.inventory_id = i.id) as cases_count
            FROM inventories i
            JOIN funds f ON f.id = i.fund_id
            ORDER BY i.number::INT
        """)
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/archive/inventories/{inventory_id}", tags=["archive"], summary="Опись с делами")
async def get_inventory(inventory_id: int):
    db = await get_db()
    try:
        inv = await db.fetchrow("""
            SELECT i.*, f.code as fund_code, f.name as fund_name
            FROM inventories i JOIN funds f ON f.id = i.fund_id
            WHERE i.id = $1
        """, inventory_id)
        if not inv:
            return resp({"error": "не найдено"})
        cases = await db.fetch("""
            SELECT c.*,
                   (SELECT COUNT(*) FROM archive_units au WHERE au.case_id = c.id) as units_count
            FROM cases c
            WHERE c.inventory_id = $1
            ORDER BY c.title
        """, inventory_id)
        return resp({"inventory": dict(inv), "cases": [dict(c) for c in cases]})
    finally:
        await db.close()

@app.get("/archive/cases/{case_id}", tags=["archive"], summary="Дело с единицами хранения")
async def get_case(case_id: int):
    db = await get_db()
    try:
        case = await db.fetchrow("""
            SELECT c.*, i.number as inv_number, i.title as inv_title,
                   f.code as fund_code, f.name as fund_name
            FROM cases c
            JOIN inventories i ON i.id = c.inventory_id
            JOIN funds f ON f.id = i.fund_id
            WHERE c.id = $1
        """, case_id)
        if not case:
            return resp({"error": "не найдено"})
        units = await db.fetch("""
            SELECT au.*, d.title as doc_title, d.doc_type, d.file_path,
                   d.archive_ref, d.date_created, d.author, d.description,
                   d.source, d.is_original, d.id as doc_id
            FROM archive_units au
            LEFT JOIN documents d ON d.id = au.object_id AND au.object_type = 'document'
            WHERE au.case_id = $1
            ORDER BY au.unit_number::INT
        """, case_id)
        result = []
        for r in units:
            d = dict(r)
            if d.get("file_path"):
                d["url"] = public_url(d["file_path"])
            result.append(d)
        return resp({"case": dict(case), "units": result})
    finally:
        await db.close()

class CaseIn(BaseModel):
    inventory_id: int
    number: Optional[str] = None
    title: str
    description: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    project_group: Optional[str] = None

@app.post("/archive/cases", tags=["archive"], summary="Создать дело")
async def create_case(c: CaseIn):
    db = await get_db()
    try:
        if not c.number:
            row_count = await db.fetchval(
                "SELECT COUNT(*) FROM cases WHERE inventory_id=$1", c.inventory_id)
            c.number = str(row_count + 1)
        row = await db.fetchrow("""
            INSERT INTO cases (inventory_id, number, title, description, date_from, date_to, project_group)
            VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id
        """, c.inventory_id, c.number, c.title, c.description,
            date_or_none(c.date_from), date_or_none(c.date_to), c.project_group)
        return resp({"id": row["id"], "status": "ok"})
    finally:
        await db.close()

@app.put("/archive/cases/{case_id}", tags=["archive"], summary="Обновить дело")
async def update_case(case_id: int, c: CaseIn):
    db = await get_db()
    try:
        await db.execute("""
            UPDATE cases SET title=$1, description=$2, date_from=$3, date_to=$4, project_group=$5
            WHERE id=$6
        """, c.title, c.description, date_or_none(c.date_from), date_or_none(c.date_to),
            c.project_group, case_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

@app.patch("/archive/cases/{case_id}/show-on-site", tags=["archive"], summary="Переключить показ на сайте")
async def toggle_show_on_site(case_id: int, show: bool = Query(...)):
    db = await get_db()
    try:
        await db.execute("UPDATE cases SET show_on_site=$1 WHERE id=$2", show, case_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

@app.get("/site/data", tags=["archive"], summary="Данные публичного сайта")
async def get_site_data():
    db = await get_db()
    try:
        rows = await db.fetch("""
            SELECT c.id, c.title, c.description, c.date_from, c.date_to,
                   c.project_group, c.number,
                   i.id as inventory_id, i.title as inventory_title, i.number as inventory_number,
                   f.code as fund_code, f.name as fund_name,
                   (SELECT COUNT(*) FROM archive_units au WHERE au.case_id = c.id) as units_count
            FROM cases c
            JOIN inventories i ON i.id = c.inventory_id
            JOIN funds f ON f.id = i.fund_id
            WHERE c.show_on_site = true
            ORDER BY i.number::INT, c.project_group NULLS LAST, c.date_from NULLS LAST, c.title
        """)
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.delete("/archive/cases/{case_id}", tags=["archive"], summary="Удалить дело")
async def delete_case(case_id: int):
    db = await get_db()
    try:
        await db.execute("DELETE FROM cases WHERE id=$1", case_id)
        return resp({"status": "ok"})
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
    inventory_case_id: Optional[int] = None

@app.get("/persons", tags=["persons"], summary="Список персон")
async def list_persons(limit: int = 50, offset: int = 0):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT id, last_name, first_name, patronymic, roles, born, inventory_case_id FROM persons ORDER BY last_name LIMIT $1 OFFSET $2",
            limit, offset
        )
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/persons/{person_id}", tags=["persons"], summary="Карточка персоны")
async def get_person(person_id: int):
    db = await get_db()
    try:
        person = await db.fetchrow("SELECT * FROM persons WHERE id = $1", person_id)
        if not person:
            return resp({"error": "не найдено"})
        productions = await db.fetch("""
            SELECT p.id, p.title, p.season, p.theater_name, p.premiere_date, pp.role_in_production
            FROM productions p
            JOIN production_persons pp ON pp.production_id = p.id
            WHERE pp.person_id = $1
            ORDER BY p.premiere_date DESC NULLS LAST
        """, person_id)
        documents = await db.fetch("""
            SELECT d.id, d.title, d.doc_type, d.file_path, d.date_created,
                   d.description, d.author, d.archive_ref, d.source, d.is_original
            FROM documents d
            JOIN object_relations r ON r.source_id = d.id
            WHERE r.source_type='document' AND r.target_type='person' AND r.target_id=$1
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

@app.post("/persons", tags=["persons"], summary="Создать персону")
async def create_person(p: PersonIn):
    db = await get_db()
    try:
        row = await db.fetchrow("""
            INSERT INTO persons (last_name, first_name, patronymic, born, died, roles, bio, inventory_case_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id
        """, p.last_name, p.first_name, p.patronymic,
            date_or_none(p.born), date_or_none(p.died), p.roles, p.bio, p.inventory_case_id)
        return resp({"id": row["id"], "status": "ok"})
    finally:
        await db.close()

@app.put("/persons/{person_id}", tags=["persons"], summary="Обновить персону")
async def update_person(person_id: int, p: PersonIn):
    db = await get_db()
    try:
        await db.execute("""
            UPDATE persons SET last_name=$1, first_name=$2, patronymic=$3,
            born=$4, died=$5, roles=$6, bio=$7, inventory_case_id=$8 WHERE id=$9
        """, p.last_name, p.first_name, p.patronymic,
            date_or_none(p.born), date_or_none(p.died), p.roles, p.bio,
            p.inventory_case_id, person_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

@app.delete("/persons/{person_id}", tags=["persons"], summary="Удалить персону")
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
    theater_name: Optional[str] = None
    stage_designer: Optional[str] = None
    costume_designer: Optional[str] = None
    composer: Optional[str] = None
    lighting_designer: Optional[str] = None
    inventory_case_id: Optional[int] = None

@app.get("/productions", tags=["productions"], summary="Список спектаклей")
async def list_productions(limit: int = 50, offset: int = 0):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT id, title, season, genre, premiere_date, theater_name, inventory_case_id FROM productions ORDER BY premiere_date DESC NULLS LAST LIMIT $1 OFFSET $2",
            limit, offset
        )
        return resp([dict(r) for r in rows])
    finally:
        await db.close()

@app.get("/productions/{production_id}", tags=["productions"], summary="Карточка спектакля")
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
            ORDER BY pp.role_in_production, p.last_name
        """, production_id)
        documents = await db.fetch("""
            SELECT d.id, d.title, d.doc_type, d.file_path, d.date_created,
                   d.description, d.author, d.archive_ref, d.source, d.is_original
            FROM documents d
            JOIN object_relations r ON r.source_id = d.id
            WHERE r.source_type='document' AND r.target_type='production' AND r.target_id=$1
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

@app.post("/productions", tags=["productions"], summary="Создать спектакль")
async def create_production(p: ProductionIn):
    db = await get_db()
    try:
        row = await db.fetchrow("""
            INSERT INTO productions (title, subtitle, playwright, genre, season,
                premiere_date, last_date, description, theater_name,
                stage_designer, costume_designer, composer, lighting_designer, inventory_case_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14) RETURNING id
        """, p.title, p.subtitle, p.playwright, p.genre, p.season,
            date_or_none(p.premiere_date), date_or_none(p.last_date), p.description,
            p.theater_name, p.stage_designer, p.costume_designer, p.composer,
            p.lighting_designer, p.inventory_case_id)
        return resp({"id": row["id"], "status": "ok"})
    finally:
        await db.close()

@app.put("/productions/{production_id}", tags=["productions"], summary="Обновить спектакль")
async def update_production(production_id: int, p: ProductionIn):
    db = await get_db()
    try:
        await db.execute("""
            UPDATE productions SET title=$1, subtitle=$2, playwright=$3, genre=$4,
            season=$5, premiere_date=$6, last_date=$7, description=$8, theater_name=$9,
            stage_designer=$10, costume_designer=$11, composer=$12,
            lighting_designer=$13, inventory_case_id=$14
            WHERE id=$15
        """, p.title, p.subtitle, p.playwright, p.genre, p.season,
            date_or_none(p.premiere_date), date_or_none(p.last_date), p.description,
            p.theater_name, p.stage_designer, p.costume_designer, p.composer,
            p.lighting_designer, p.inventory_case_id, production_id)
        return resp({"status": "ok"})
    finally:
        await db.close()

@app.delete("/productions/{production_id}", tags=["productions"], summary="Удалить спектакль")
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

@app.post("/productions/{production_id}/persons", tags=["productions"], summary="Добавить участника")
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

@app.delete("/productions/{production_id}/persons/{person_id}", tags=["productions"], summary="Убрать участника")
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

DOC_TYPES = ["фотография", "афиша", "программка", "видеозапись", "рецензия",
             "текст пьесы", "договор", "интервью", "лекция", "публикация",
             "концепция", "черновик", "переписка", "другое"]

@app.get("/doc-types", tags=["documents"], summary="Типы документов")
async def get_doc_types():
    return resp(DOC_TYPES)

@app.get("/documents", tags=["documents"], summary="Список документов")
async def list_documents(limit: int = 100, offset: int = 0):
    db = await get_db()
    try:
        rows = await db.fetch(
            "SELECT id, title, doc_type, date_created, author, file_path, archive_ref, source, is_original FROM documents ORDER BY created_at DESC LIMIT $1 OFFSET $2",
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

@app.get("/documents/{doc_id}", tags=["documents"], summary="Карточка документа")
async def get_document(doc_id: int):
    db = await get_db()
    try:
        doc = await db.fetchrow("SELECT * FROM documents WHERE id=$1", doc_id)
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

@app.post("/upload/document", tags=["documents"], summary="Загрузить документ")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(""),
    doc_type: str = Form("другое"),
    description: str = Form(""),
    author: str = Form(""),
    date_created: str = Form(""),
    source: str = Form(""),
    is_original: str = Form("true"),
    production_ids: str = Form("[]"),
    person_ids: str = Form("[]"),
    inventory_id: str = Form(""),
    case_id: str = Form(""),
):
    file_bytes = await file.read()
    file_path = save_file(file_bytes, file.filename)
    ext = Path(file.filename).suffix.lower()
    prod_ids = json.loads(production_ids)
    pers_ids = json.loads(person_ids)
    inv_id = int(inventory_id) if inventory_id.strip() else None
    c_id = int(case_id) if case_id.strip() else None
    is_orig = is_original.lower() != "false"

    db = await get_db()
    try:
        row = await db.fetchrow("""
            INSERT INTO documents (title, doc_type, description, author, date_created,
                file_path, file_format, source, is_original, inventory_id)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id
        """, title or file.filename, doc_type,
            description or None, author or None,
            date_or_none(date_created), file_path, ext,
            source or None, is_orig, inv_id)

        doc_id = row["id"]
        use_date = date_or_none(date_created) or datetime.date.today()

        if c_id:
            # Кладём прямо в указанное дело
            unit_count = await db.fetchval(
                "SELECT COUNT(*) FROM archive_units WHERE case_id=$1", c_id)
            unit_num = str(unit_count + 1)
            unit_id = await db.fetchval("""
                INSERT INTO archive_units (case_id, unit_number, title, object_type, object_id)
                VALUES ($1,$2,$3,'document',$4) RETURNING id
            """, c_id, unit_num, title or file.filename, doc_id)
            ref_row = await db.fetchrow("""
                SELECT f.code || ' Оп.' || i.number || ' Д.' || c.number || ' Ед.хр.' || $2 as ref
                FROM archive_units au
                JOIN cases c ON c.id = au.case_id
                JOIN inventories i ON i.id = c.inventory_id
                JOIN funds f ON f.id = i.fund_id
                WHERE au.id = $1
            """, unit_id, unit_num)
            await db.execute(
                "UPDATE documents SET archive_unit_id=$1, archive_ref=$2 WHERE id=$3",
                unit_id, ref_row["ref"] if ref_row else None, doc_id)
        else:
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

        ref_row = await db.fetchrow("SELECT archive_ref FROM documents WHERE id=$1", doc_id)
        return resp({"id": doc_id, "url": public_url(file_path),
                     "archive_ref": ref_row["archive_ref"] if ref_row else None, "status": "ok"})
    finally:
        await db.close()

@app.put("/documents/{doc_id}", tags=["documents"], summary="Обновить документ")
async def update_document(
    doc_id: int,
    title: str = Form(""),
    doc_type: str = Form("другое"),
    description: str = Form(""),
    author: str = Form(""),
    date_created: str = Form(""),
    source: str = Form(""),
    is_original: str = Form("true"),
    production_ids: str = Form("[]"),
    person_ids: str = Form("[]"),
    inventory_id: str = Form(""),
    case_id: str = Form(""),
):
    prod_ids = json.loads(production_ids)
    pers_ids = json.loads(person_ids)
    inv_id = int(inventory_id) if inventory_id.strip() else None
    c_id = int(case_id) if case_id.strip() else None
    is_orig = is_original.lower() != "false"

    db = await get_db()
    try:
        await db.execute("""
            UPDATE documents SET title=$1, doc_type=$2, description=$3, author=$4,
            date_created=$5, source=$6, is_original=$7, inventory_id=$8 WHERE id=$9
        """, title, doc_type, description or None, author or None,
            date_or_none(date_created), source or None, is_orig, inv_id, doc_id)

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

@app.delete("/documents/{doc_id}", tags=["documents"], summary="Удалить документ")
async def delete_document(doc_id: int):
    db = await get_db()
    try:
        row = await db.fetchrow("SELECT file_path FROM documents WHERE id=$1", doc_id)
        if row and row["file_path"]:
            delete_file(row["file_path"])
        await db.execute("DELETE FROM object_relations WHERE source_type='document' AND source_id=$1", doc_id)
        await db.execute("UPDATE documents SET archive_unit_id=NULL WHERE id=$1", doc_id)
        await db.execute("DELETE FROM archive_units WHERE object_type='document' AND object_id=$1", doc_id)
        await db.execute("DELETE FROM documents WHERE id=$1", doc_id)
        return resp({"status": "ok"})
    finally:
        await db.close()
