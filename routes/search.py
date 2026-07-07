from fastapi import APIRouter, HTTPException
from backend.models.schemas import SearchTextRequest, SearchResponse, HistoryResponse, SearchResult
from backend.services.ai_service import generate_recommendation
from backend.services.price_service import search_prices
from backend.database.db import save_search, get_history, delete_history_item, clear_all_history
import logging
from datetime import datetime

logger = logging.getLogger("routes.search")
router = APIRouter()

# Max file size limit: 5MB
MAX_FILE_SIZE = 5 * 1024 * 1024

@router.get("/health")
async def health():
    return {"status": "ok"}

@router.post("/search-text", response_model=SearchResponse)
async def search_text(request: SearchTextRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Search query cannot be empty")
    
    try:
        # Step 1: Search prices
        product_name, results, confidence = search_prices(query)
        
        # Step 2: Generate AI recommendation
        recommendation = generate_recommendation(product_name, results)
        
        # Structure results list
        search_results = [
            SearchResult(
                platform=r["platform"],
                price=r["price"],
                currency=r["currency"],
                link=r["link"]
            ) for r in results
        ]
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M") + " IST"
        
        response_obj = SearchResponse(
            product=product_name,
            confidence_score=confidence,
            search_timestamp=timestamp,
            results=search_results,
            recommendation=recommendation
        )
        
        # Step 3: Save to DB history with serialized results
        try:
            results_json = response_obj.model_dump_json()
        except AttributeError:
            results_json = response_obj.json()
        save_search(query=query, product_name=product_name, search_type="text", results=results_json)
        
        return response_obj
    except Exception as e:
        logger.error(f"Error in search-text API: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred while processing your search. Please try again."
        )



@router.get("/history", response_model=HistoryResponse)
async def fetch_history():
    try:
        history_list = get_history()
        return HistoryResponse(history=history_list)
    except Exception as e:
        logger.error(f"Error fetching search history: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve search history."
        )

@router.delete("/history/{item_id}")
async def delete_item(item_id: int):
    try:
        delete_history_item(item_id)
        return {"status": "success", "message": "History item deleted"}
    except Exception as e:
        logger.error(f"Error deleting history item: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not delete history item."
        )

@router.delete("/history")
async def clear_history():
    try:
        clear_all_history()
        return {"status": "success", "message": "All history cleared"}
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        raise HTTPException(
            status_code=500,
            detail="Could not clear history."
        )
