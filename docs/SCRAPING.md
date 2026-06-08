# NexusMind — Web Scraping & Crawling Guide

คู่มือนี้อธิบายระบบ scraping และ crawling ของ NexusMind ตั้งแต่ architecture ไปจนถึงคำสั่งจริงที่ใช้งาน

---

## สารบัญ

1. [Architecture Overview](#1-architecture-overview)
2. [Components](#2-components)
3. [Configuration](#3-configuration)
4. [API Endpoints](#4-api-endpoints)
5. [curl Examples](#5-curl-examples)
6. [Python Examples (direct service call)](#6-python-examples)
7. [Celery Task Examples](#7-celery-task-examples)
8. [Docker Commands](#8-docker-commands)
9. [Flow Diagram](#9-flow-diagram)
10. [FAQ / Troubleshooting](#10-faq--troubleshooting)

---

## 1. Architecture Overview

```
User / API Request
        │
        ▼
  FastAPI Route  ─────────────────────────────────────────────┐
  POST /api/v1/documents/crawl                                 │
        │                                                      │
        ▼                                                      │
  Celery Task: crawl_and_ingest                                │
  (runs in worker container)                                   │
        │                                                      │
        ▼                                                      │
  WebCrawler  ◄─────── RobotsCache ◄─── robots.txt per domain │
        │                                                      │
        │◄──────────── SitemapParser ◄─── /sitemap.xml        │
        │                                                      │
   CrawledPage[]  (url, title, content, links, meta)          │
        │                                                      │
        ▼ (one Celery task per page)                           │
  Celery Task: ingest_document                                 │
        │                                                      │
        ├── DocumentProcessor  → chunks (512 tokens, 64 overlap)
        ├── Embedder           → float32 vectors (384-dim BGE)
        ├── VectorStore        → ChromaDB upsert
        └── PostgreSQL DB      → Document + DocumentChunk rows
```

ข้อมูล flow สั้น ๆ:
1. Client ส่ง `POST /documents/crawl` พร้อม URL
2. FastAPI สร้าง Celery task แล้วตอบ `202 Accepted` ทันที (non-blocking)
3. Worker crawl หน้าเว็บ → ตรวจ robots.txt → ดึง sitemap (ถ้าเปิด)
4. แต่ละหน้าที่ crawl ได้จะถูก queue เป็น `ingest_document` task แยก
5. Ingest task แบ่ง chunk → embed → เก็บใน ChromaDB + PostgreSQL

---

## 2. Components

### 2.1 `WebCrawler` — [backend/app/services/crawler.py](../backend/app/services/crawler.py)

Breadth-first crawler ที่ใช้ `httpx` + `BeautifulSoup4`

| คลาส / ฟังก์ชัน | หน้าที่ |
|---|---|
| `WebCrawler.crawl()` | จุดเริ่มต้นหลัก — crawl จาก URL เดียว |
| `WebCrawler._fetch()` | ดึง HTML 1 หน้า พร้อม semaphore (concurrent limit) |
| `WebCrawler._extract_text()` | ลบ script/style/nav แล้วดึง plain text |
| `WebCrawler._extract_links()` | ดึง `<a href>` ทั้งหมด deduplicate |
| `WebCrawler._extract_meta()` | ดึง OG tags, author, description, published date |
| `RobotsCache` | Cache robots.txt ต่อ domain (fetch ครั้งเดียว) |
| `SitemapParser` | Parse `/sitemap.xml` รวมถึง sitemap index |

**Parameters ของ `crawl()`:**

```python
async def crawl(
    start_url: str,
    max_depth: int = 3,       # ลึกสุดกี่ hop จาก start_url
    max_pages: int = 100,     # จำนวน page สูงสุด
    follow_external: bool = False,  # ตาม link ข้าม domain ได้ไหม
    use_sitemap: bool = False,      # seed queue จาก sitemap.xml
    respect_robots: bool = True,    # เชื่อฟัง robots.txt ไหม
) -> list[CrawledPage]
```

**`CrawledPage` dataclass:**

```python
@dataclass
class CrawledPage:
    url: str
    title: str
    content: str           # plain text ที่ clean แล้ว
    links: list[str]       # outgoing links จาก page
    status_code: int
    meta: PageMeta         # description, author, published_at, og_title, keywords
```

---

### 2.2 `ArticleScraper` — [backend/app/services/scraper.py](../backend/app/services/scraper.py)

ดึง structured data จาก URL เดียว — เหมาะสำหรับ blog post / news article

```python
@dataclass
class Article:
    url: str
    title: str
    content: str           # main body text (ตัด sidebar/nav ออก)
    author: str
    published_at: datetime | None
    description: str       # meta description
    tags: list[str]        # meta keywords
    images: list[str]      # absolute image URLs (max 10)
    word_count: int
```

**Content selector ที่ใช้ (เรียงตาม priority):**

```
article  →  [role='main']  →  main  →  .post-content
.article-body  →  .entry-content  →  #content  →  #main  →  <body>
```

---

### 2.3 `FeedScraper` — [backend/app/services/scraper.py](../backend/app/services/scraper.py)

Parse RSS / Atom feed ต้องติดตั้ง `feedparser`:

```bash
pip install feedparser
```

```python
@dataclass
class FeedItem:
    url: str
    title: str
    summary: str           # stripped HTML
    author: str
    published_at: datetime | None
```

---

## 3. Configuration

ตัวแปรทั้งหมดกำหนดใน `.env` (ดู [backend/app/core/config.py](../backend/app/core/config.py))

```env
# ── Crawler ───────────────────────────────────────────────
CRAWLER_MAX_DEPTH=3          # ความลึกสูงสุดของการ crawl
CRAWLER_MAX_PAGES=100        # จำนวนหน้าสูงสุดต่อ job
CRAWLER_TIMEOUT=30           # HTTP timeout (วินาที)
CRAWLER_USER_AGENT=NexusMind-Bot/0.1   # User-Agent header

# ── Celery / Redis ────────────────────────────────────────
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# ── Embeddings ────────────────────────────────────────────
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
EMBEDDING_DIMENSION=384

# ── Chunking ──────────────────────────────────────────────
CHUNK_SIZE=512               # tokens ต่อ chunk
CHUNK_OVERLAP=64             # token overlap ระหว่าง chunks
```

---

## 4. API Endpoints

Base URL: `http://localhost:8000/api/v1`

### 4.1 Start a crawl job

```
POST /documents/crawl
```

**Request body:**

```json
{
  "url": "https://example.com",
  "max_depth": 2,
  "max_pages": 50,
  "follow_external": false,
  "use_sitemap": false,
  "respect_robots": true
}
```

| Field | Type | Default | คำอธิบาย |
|---|---|---|---|
| `url` | string (URL) | required | URL เริ่มต้นที่จะ crawl |
| `max_depth` | int | 2 | ลึกสูงสุดจาก start URL |
| `max_pages` | int | 50 | จำนวนหน้าสูงสุด |
| `follow_external` | bool | false | ตาม link ออก domain ด้วยไหม |
| `use_sitemap` | bool | false | อ่าน sitemap.xml ก่อน crawl |
| `respect_robots` | bool | true | เชื่อฟัง robots.txt |

**Response `202 Accepted`:**

```json
{
  "task_id": "f3b2a1c4-...",
  "start_url": "https://example.com"
}
```

---

### 4.2 Ingest a single document (text)

```
POST /documents/
```

```json
{
  "title": "My Document",
  "content": "Full text content here...",
  "mime_type": "text/plain"
}
```

---

### 4.3 Upload a text file

```
POST /documents/upload
```

Multipart form, field name: `file`

---

### 4.4 List documents

```
GET /documents/?page=1&page_size=20
```

---

### 4.5 Get a document

```
GET /documents/{document_id}
```

---

### 4.6 Delete a document

```
DELETE /documents/{document_id}
```

ลบออกจาก PostgreSQL **และ** ChromaDB พร้อมกัน

---

## 5. curl Examples

### เริ่ม crawl job

```bash
curl -X POST http://localhost:8000/api/v1/documents/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://docs.python.org/3/",
    "max_depth": 2,
    "max_pages": 30,
    "follow_external": false
  }'
```

### Crawl พร้อม sitemap + เปิด external links

```bash
curl -X POST http://localhost:8000/api/v1/documents/crawl \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com",
    "max_depth": 3,
    "max_pages": 200,
    "use_sitemap": true,
    "follow_external": true,
    "respect_robots": true
  }'
```

### Ingest ข้อความตรง ๆ

```bash
curl -X POST http://localhost:8000/api/v1/documents/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Python Basics",
    "content": "Python is a high-level programming language..."
  }'
```

### Upload ไฟล์

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -F "file=@/path/to/document.txt"
```

### ดู task result ผ่าน Celery (Flower UI)

เปิด browser: `http://localhost:5555`

---

## 6. Python Examples

### 6.1 ใช้ `WebCrawler` โดยตรง

```python
import asyncio
from app.services.crawler import WebCrawler

async def main():
    crawler = WebCrawler(
        concurrency=5,       # fetch กี่หน้าพร้อมกัน
        politeness_delay=0.5 # หน่วง 0.5 วินาทีระหว่าง request
    )

    pages = await crawler.crawl(
        start_url="https://docs.python.org/3/",
        max_depth=2,
        max_pages=20,
        use_sitemap=False,
        respect_robots=True,
    )

    for page in pages:
        print(f"[{page.status_code}] {page.title}")
        print(f"  URL: {page.url}")
        print(f"  Author: {page.meta.author}")
        print(f"  Published: {page.meta.published_at}")
        print(f"  Words: {len(page.content.split())}")
        print()

asyncio.run(main())
```

---

### 6.2 ใช้ `ArticleScraper` ดึงบทความเดียว

```python
import asyncio
from app.services.scraper import ArticleScraper

async def main():
    scraper = ArticleScraper()

    article = await scraper.scrape("https://example.com/blog/my-post")

    if article:
        print(f"Title   : {article.title}")
        print(f"Author  : {article.author}")
        print(f"Date    : {article.published_at}")
        print(f"Words   : {article.word_count}")
        print(f"Tags    : {article.tags}")
        print(f"Images  : {article.images[:3]}")
        print(f"Preview : {article.content[:200]}...")

asyncio.run(main())
```

---

### 6.3 Scrape หลาย URL พร้อมกัน

```python
import asyncio
from app.services.scraper import ArticleScraper

urls = [
    "https://example.com/post/1",
    "https://example.com/post/2",
    "https://example.com/post/3",
]

async def main():
    scraper = ArticleScraper()
    articles = await scraper.scrape_many(urls, concurrency=3)

    print(f"Scraped {len(articles)} articles")
    for a in articles:
        print(f"  - {a.title} ({a.word_count} words)")

asyncio.run(main())
```

---

### 6.4 Parse RSS feed

```python
import asyncio
from app.services.scraper import FeedScraper

async def main():
    scraper = FeedScraper()

    # RSS feed เดียว
    items = await scraper.fetch("https://news.ycombinator.com/rss")

    for item in items[:5]:
        print(f"{item.published_at}  {item.title}")
        print(f"  {item.url}")

    # หลาย feed พร้อมกัน
    all_items = await scraper.fetch_many([
        "https://news.ycombinator.com/rss",
        "https://feeds.feedburner.com/TechCrunch",
    ])
    print(f"Total items: {len(all_items)}")

asyncio.run(main())
```

---

### 6.5 Queue Celery task โดยตรง (จาก Python)

```python
from app.workers.tasks import crawl_and_ingest, ingest_document

# สั่ง crawl ทั้ง site
result = crawl_and_ingest.delay(
    "https://example.com",
    max_depth=2,
    max_pages=50,
    follow_external=False,
    use_sitemap=True,
    respect_robots=True,
)
print("Task ID:", result.id)

# ดู status
print("Status:", result.status)   # PENDING / STARTED / SUCCESS / FAILURE

# รอผล (blocking)
output = result.get(timeout=300)
print("Result:", output)
# {'queued': 42, 'start_url': 'https://example.com'}
```

---

## 7. Celery Task Examples

### เรียก task จาก Python shell

```python
# เปิด Python shell ใน container
docker compose exec worker python

>>> from app.workers.tasks import crawl_and_ingest
>>> t = crawl_and_ingest.delay("https://example.com", 2, 30, False)
>>> t.id
'abc123...'
>>> t.get(timeout=120)
{'queued': 18, 'start_url': 'https://example.com'}
```

### ดู task result จาก Redis CLI

```bash
# เข้า Redis container
docker compose exec redis redis-cli

# ดู keys ทั้งหมด
127.0.0.1:6379> KEYS celery-task-meta-*

# ดูผลของ task หนึ่ง
127.0.0.1:6379> GET celery-task-meta-<task_id>
```

### ดู active tasks จาก Celery inspect

```bash
docker compose exec worker celery -A app.workers.tasks inspect active
docker compose exec worker celery -A app.workers.tasks inspect reserved
docker compose exec worker celery -A app.workers.tasks inspect stats
```

---

## 8. Docker Commands

### เริ่ม services ทั้งหมด

```bash
# Development (พร้อม hot reload)
docker compose -f docker-compose.dev.yml up

# Production
docker compose up -d
```

### ดู logs

```bash
# ดู log ของ worker (เห็น crawl progress)
docker compose logs -f worker

# ดู log ของ backend API
docker compose logs -f backend

# ดูทุก service
docker compose logs -f
```

### Scale workers

```bash
# เพิ่ม worker 3 instance (crawl เร็วขึ้น)
docker compose up -d --scale worker=3
```

### รัน Celery worker ด้วยมือ (นอก Docker)

```bash
# ติดตั้ง dependencies
pip install -r backend/requirements.txt

# เริ่ม worker
cd backend
celery -A app.workers.tasks worker \
  --loglevel=info \
  --concurrency=4 \
  -Q celery

# เปิด Flower monitoring UI (port 5555)
celery -A app.workers.tasks flower
```

### Alembic database migrations

```bash
# สร้าง migration ใหม่
docker compose exec backend alembic revision --autogenerate -m "add_scrape_field"

# Apply migrations
docker compose exec backend alembic upgrade head

# ย้อนกลับ 1 version
docker compose exec backend alembic downgrade -1
```

---

## 9. Flow Diagram

### Crawl + Ingest ทีละขั้น

```
POST /documents/crawl
  {"url": "https://example.com", "max_depth": 2}
          │
          ▼
  [FastAPI]  สร้าง Celery task ทันที
          │
          ▼  202 Accepted
  {"task_id": "abc123"}   ◄── Client รับทันที ไม่ต้องรอ
          │
          │ (background)
          ▼
  [Celery Worker]  crawl_and_ingest task
          │
          ├─► robots.txt check  (example.com/robots.txt)
          ├─► sitemap.xml parse (ถ้า use_sitemap=true)
          │
          ▼
  Queue: [page1, page2, page3, ...] (BFS, max_depth=2)
          │
          ▼ ทีละหน้า (concurrent ไม่เกิน 5)
  _fetch(url)
    ├── GET https://example.com/
    ├── BeautifulSoup parse
    ├── extract text (ลบ nav/footer/script)
    ├── extract links (ต่อคิว)
    └── extract meta (author, date, og:*)
          │
          ▼ สำหรับแต่ละหน้าที่ crawl ได้
  ingest_document.delay(doc_id, content, title, meta)
          │
          ├── DocumentProcessor.process()
          │     ├── clean text
          │     ├── detect language
          │     └── split → chunks (512 tokens)
          │
          ├── Embedder.embed(chunks)
          │     └── BAAI/bge-small-en-v1.5 → [384-dim vectors]
          │
          ├── VectorStore.upsert()  → ChromaDB
          │
          └── PostgreSQL
                ├── Document (status=INDEXED)
                └── DocumentChunk × N
```

---

## 10. FAQ / Troubleshooting

### Q: Crawl ติด robots.txt บาง URL

**ตรวจสอบ:**
```bash
curl https://example.com/robots.txt
```
ถ้าต้องการ bypass (ระวัง terms of service):
```json
{"url": "...", "respect_robots": false}
```

---

### Q: Crawl ช้ามาก

สาเหตุหลัก: `politeness_delay=0.5` (หน่วง 0.5 วิต่อ request)

ปรับใน code ตอนสร้าง `WebCrawler`:
```python
crawler = WebCrawler(concurrency=10, politeness_delay=0.2)
```

หรือ scale worker:
```bash
docker compose up -d --scale worker=4
```

---

### Q: หน้าเว็บที่ crawl ได้มีแค่ JavaScript skeleton (ไม่มีเนื้อหา)

`httpx` ไม่ render JavaScript — ต้องใช้ Playwright:

```bash
pip install playwright
playwright install chromium
```

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch()
    page = await browser.new_page()
    await page.goto("https://spa-site.com")
    await page.wait_for_load_state("networkidle")
    html = await page.content()
    await browser.close()

# แล้วส่ง html เข้า BeautifulSoup ตามปกติ
```

---

### Q: Task status ดูได้ที่ไหน

```bash
# Flower UI (ดีที่สุด)
open http://localhost:5555

# Redis โดยตรง
docker compose exec redis redis-cli GET celery-task-meta-<task_id>
```

---

### Q: FeedScraper ขึ้น feedparser_not_installed

```bash
pip install feedparser
# หรือใน Docker
docker compose exec backend pip install feedparser
# แล้วเพิ่มในไฟล์ requirements.txt
echo "feedparser>=6.0" >> backend/requirements.txt
```

---

### Q: ดู chunk และ embedding ใน DB

```bash
# เข้า PostgreSQL
docker compose exec db psql -U nexusmind -d nexusmind

-- ดู documents
SELECT id, title, status, chunk_count, created_at FROM documents LIMIT 10;

-- ดู chunks ของ document หนึ่ง
SELECT chunk_index, token_count, LEFT(content, 100) as preview
FROM document_chunks
WHERE document_id = '<uuid>'
ORDER BY chunk_index;
```

---

*สร้างโดย NexusMind backend — ดูโค้ดที่ [backend/app/services/](../backend/app/services/)*
