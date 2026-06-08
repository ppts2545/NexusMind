"""
Filter Builder for Qdrant
=========================

ไฟล์นี้แปลง Python dict ธรรมดา → Qdrant Filter object

WHY ต้องมีไฟล์นี้?
-------------------
Qdrant มี filter syntax เป็นของตัวเอง ซึ่งต่างจาก MongoDB หรือ SQL
แทนที่จะให้ทุกส่วนของโค้ด import qdrant_client โดยตรง
เราสร้าง "ภาษากลาง" ขึ้นมา แล้วแปลงที่นี่ที่เดียว

ข้อดี:
  1. ถ้าเปลี่ยน vector DB จาก Qdrant → Pinecone/Weaviate
     แก้แค่ไฟล์นี้ ส่วนอื่นไม่ต้องรู้เลย
  2. syntax ที่ใช้ทั่วโปรเจกต์เป็นแบบเดียวกัน
  3. ง่ายต่อการ test

SYNTAX ที่รองรับ (Python dict)
--------------------------------
# ค่าเดียว (exact match)
{"category": "thai_news"}

# หลายค่า (match any)
{"category": {"$in": ["thai_news", "thai_finance"]}}

# หลาย field พร้อมกัน (AND)
{"category": "thai_news", "language": "th"}

# ผสมกัน
{"category": {"$in": ["thai_news"]}, "language": "th"}

แปลงเป็น Qdrant:
-----------------
{"category": "thai_news"}
  → Filter(must=[FieldCondition(key="category", match=MatchValue(value="thai_news"))])

{"category": {"$in": ["thai_news", "thai_finance"]}}
  → Filter(must=[FieldCondition(key="category", match=MatchAny(any=["thai_news", "thai_finance"]))])

{"category": "thai_news", "language": "th"}
  → Filter(must=[
        FieldCondition(key="category", match=MatchValue(value="thai_news")),
        FieldCondition(key="language", match=MatchValue(value="th")),
    ])
"""
from __future__ import annotations

from typing import Any


def build_qdrant_filter(filters: dict[str, Any] | None):
    """
    แปลง Python dict → Qdrant Filter object

    Parameters
    ----------
    filters : dict หรือ None
        ถ้า None → return None (ไม่ filter = ค้นทั้ง collection)

    Returns
    -------
    qdrant_client.models.Filter หรือ None
    """
    if not filters:
        return None

    # import ไว้ใน function เพื่อไม่ให้ crash ตอน import
    # ถ้า qdrant_client ไม่ได้ install (เช่น ตอน run tests แบบ unit test)
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue  # type: ignore[import]

    conditions = []

    for field_name, value in filters.items():

        if isinstance(value, dict):
            # value เป็น dict → มี operator เช่น {"$in": [...]}
            operator = next(iter(value))

            if operator == "$in":
                # {"$in": ["thai_news", "thai_finance"]}
                # → FieldCondition match any ใน list
                values_list = value["$in"]
                conditions.append(
                    FieldCondition(
                        key=field_name,
                        match=MatchAny(any=values_list),
                    )
                )

            else:
                # operator ที่ยังไม่รองรับ — skip แล้ว log warning
                import logging
                logging.warning(f"[FilterBuilder] Unsupported operator '{operator}' for field '{field_name}' — skipped")

        else:
            # value เป็น string/int/bool ธรรมดา → exact match
            # {"category": "thai_news"} หรือ {"language": "th"}
            conditions.append(
                FieldCondition(
                    key=field_name,
                    match=MatchValue(value=value),
                )
            )

    if not conditions:
        return None

    # must = AND ทุก condition ต้องผ่านหมด
    return Filter(must=conditions)


def build_intent_filter(
    categories: list[str] | None = None,
    domains: list[str] | None = None,
    language: str | None = None,
) -> dict[str, Any] | None:
    """
    Helper สร้าง filter dict จาก intent classification result

    เรียกใช้จาก retriever.py หลังได้ผลลัพธ์จาก IntentClassifier

    Parameters
    ----------
    categories : list[str] | None
        เช่น ["thai_news", "thai_finance"]
        ถ้า None = ไม่ filter ตาม category

    domains : list[str] | None
        เช่น ["matichon.co.th", "thairath.co.th"]
        ถ้า None = ไม่ filter ตาม domain

    language : str | None
        เช่น "th" หรือ "en"
        ถ้า None = ไม่ filter ตาม language

    Returns
    -------
    dict หรือ None
        None ถ้าไม่มี filter เลย (ค้นทั้งหมด)

    ตัวอย่างผลลัพธ์:
    ----------------
    build_intent_filter(categories=["thai_news"], language="th")
    → {"category": {"$in": ["thai_news"]}, "language": "th"}

    build_intent_filter(domains=["matichon.co.th", "bot.or.th"])
    → {"source_domain": {"$in": ["matichon.co.th", "bot.or.th"]}}
    """
    result: dict[str, Any] = {}

    if categories:
        if len(categories) == 1:
            # ถ้า category เดียว ใช้ exact match (เร็วกว่า $in เล็กน้อย)
            result["category"] = categories[0]
        else:
            result["category"] = {"$in": categories}

    if domains:
        if len(domains) == 1:
            result["source_domain"] = domains[0]
        else:
            result["source_domain"] = {"$in": domains}

    if language:
        result["language"] = language

    return result if result else None
