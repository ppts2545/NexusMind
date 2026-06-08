"""
Source Registry — maps topic categories to trusted URLs.

Add new categories and sources here. The intent classifier routes
queries to the matching category, and the retriever filters results
to only documents crawled from those domains.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceEntry:
    url: str
    language: str = "en"
    description: str = ""
    crawl_depth: int = 2
    crawl_pages: int = 200


@dataclass
class TopicCategory:
    name: str
    description: str                    # shown to the intent classifier
    keywords: list[str]                 # extra hints for classification
    sources: list[SourceEntry] = field(default_factory=list)

    @property
    def domains(self) -> list[str]:
        from urllib.parse import urlparse
        return [urlparse(s.url).netloc for s in self.sources]

    @property
    def seed_urls(self) -> list[str]:
        return [s.url for s in self.sources]


# ---------------------------------------------------------------------------
# Registry — edit this to add / remove trusted sources per topic
# ---------------------------------------------------------------------------

REGISTRY: dict[str, TopicCategory] = {

    "thai_news": TopicCategory(
        name="thai_news",
        description="Thai news, current events, politics, economy in Thailand",
        keywords=["ข่าว", "การเมือง", "เศรษฐกิจ", "ไทย", "news", "thailand", "thai"],
        sources=[
            SourceEntry("https://www.matichon.co.th", language="th", description="มติชน"),
            SourceEntry("https://thestandard.co", language="th", description="The Standard"),
            SourceEntry("https://www.thairath.co.th", language="th", description="ไทยรัฐ"),
            SourceEntry("https://www.bangkokbiznews.com", language="th", description="กรุงเทพธุรกิจ"),
            SourceEntry("https://www.thaipbs.or.th", language="th", description="Thai PBS"),
        ],
    ),

    "thai_finance": TopicCategory(
        name="thai_finance",
        description="Thai financial markets, stocks, investment, SET, BOT monetary policy",
        keywords=["หุ้น", "ตลาดหลักทรัพย์", "การลงทุน", "ดอกเบี้ย", "ธนาคาร", "stock", "finance", "investment"],
        sources=[
            SourceEntry("https://www.bot.or.th", language="th", description="ธนาคารแห่งประเทศไทย"),
            SourceEntry("https://www.sec.or.th", language="th", description="ก.ล.ต."),
            SourceEntry("https://www.set.or.th", language="th", description="ตลาดหลักทรัพย์"),
            SourceEntry("https://www.thansettakij.com", language="th", description="ฐานเศรษฐกิจ"),
        ],
    ),

    "thai_law": TopicCategory(
        name="thai_law",
        description="Thai law, regulations, legislation, court rulings, legal advice",
        keywords=["กฎหมาย", "พระราชบัญญัติ", "ศาล", "นิติกรรม", "law", "legal", "regulation", "pdpa"],
        sources=[
            SourceEntry("https://www.ratchakitcha.soc.go.th", language="th", description="ราชกิจจานุเบกษา", crawl_depth=1),
            SourceEntry("https://ilaw.or.th", language="th", description="iLaw", crawl_depth=2),
            SourceEntry("https://www.oja.go.th", language="th", description="สำนักงานอัยการ"),
        ],
    ),

    "academic_ai": TopicCategory(
        name="academic_ai",
        description="AI, machine learning, deep learning, NLP, research papers, LLM",
        keywords=["ai", "machine learning", "deep learning", "nlp", "llm", "neural network",
                  "transformer", "rag", "fine-tuning", "research", "paper", "arxiv"],
        sources=[
            SourceEntry("https://arxiv.org/list/cs.AI/recent", language="en", description="arXiv AI", crawl_depth=1, crawl_pages=100),
            SourceEntry("https://arxiv.org/list/cs.LG/recent", language="en", description="arXiv ML", crawl_depth=1, crawl_pages=100),
            SourceEntry("https://arxiv.org/list/cs.CL/recent", language="en", description="arXiv NLP", crawl_depth=1, crawl_pages=100),
            SourceEntry("https://huggingface.co/blog", language="en", description="HuggingFace Blog"),
        ],
    ),

    "tech_docs": TopicCategory(
        name="tech_docs",
        description="Programming, software development, technical documentation, APIs, frameworks",
        keywords=["python", "javascript", "api", "framework", "library", "docker",
                  "kubernetes", "database", "code", "programming", "software", "developer"],
        sources=[
            SourceEntry("https://docs.python.org/3", language="en", description="Python Docs", crawl_depth=2),
            SourceEntry("https://fastapi.tiangolo.com", language="en", description="FastAPI Docs"),
            SourceEntry("https://docs.docker.com", language="en", description="Docker Docs"),
        ],
    ),

    "thai_government": TopicCategory(
        name="thai_government",
        description="Thai government policy, public services, official announcements",
        keywords=["รัฐบาล", "นโยบาย", "ราชการ", "government", "policy", "official"],
        sources=[
            SourceEntry("https://data.go.th", language="th", description="Open Government Data", crawl_depth=1),
            SourceEntry("https://www.thaigov.go.th", language="th", description="รัฐบาลไทย"),
        ],
    ),

    "general": TopicCategory(
        name="general",
        description="General knowledge, facts, encyclopedic information",
        keywords=["what", "how", "why", "คืออะไร", "ทำไม", "อย่างไร"],
        sources=[
            SourceEntry("https://en.wikipedia.org/wiki/Main_Page", language="en", description="Wikipedia EN", crawl_depth=1),
            SourceEntry("https://th.wikipedia.org/wiki/หน้าหลัก", language="th", description="Wikipedia TH", crawl_depth=1),
        ],
    ),
}


def get_category(name: str) -> TopicCategory | None:
    return REGISTRY.get(name)


def all_categories() -> list[TopicCategory]:
    return list(REGISTRY.values())


def all_domains() -> set[str]:
    domains: set[str] = set()
    for cat in REGISTRY.values():
        domains.update(cat.domains)
    return domains
