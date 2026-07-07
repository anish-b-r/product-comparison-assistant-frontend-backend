from pydantic import BaseModel
from typing import List, Optional

class SearchTextRequest(BaseModel):
    query: str

class SearchResult(BaseModel):
    platform: str
    price: float
    currency: str
    link: str

class SearchResponse(BaseModel):
    product: str
    confidence_score: int
    search_timestamp: str
    results: List[SearchResult]
    recommendation: str

class HistoryItem(BaseModel):
    id: int
    query: str
    product_name: str
    search_type: str
    created_at: str
    results: Optional[str] = None

class HistoryResponse(BaseModel):
    history: List[HistoryItem]
