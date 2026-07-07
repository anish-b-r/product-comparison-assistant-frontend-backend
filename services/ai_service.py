import os
import json
import logging
import urllib.parse
from typing import List, Dict

logger = logging.getLogger("ai_service")

# Try importing the Google GenAI SDK
try:
    from google import genai
    from google.genai import types
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False

def get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        if GENAI_AVAILABLE:
            return genai.Client(api_key=api_key)
    except Exception as e:
        logger.error(f"Error initializing Gemini client: {e}")
    return None

def search_prices_with_gemini(product_name: str) -> List[Dict]:
    """
    Uses Gemini 2.5 Flash with Google Search Grounding to find actual, live online 
    product prices and stores from the web in real-time.
    """
    client = get_client()
    if not client:
        logger.warning("Gemini Client is not available. Skipping Gemini Search Grounding.")
        return []
    
    try:
        prompt = (
            f"Search the web to find the actual, live online retail prices in India (INR) for the main product: '{product_name}'.\n"
            f"Identify the price on major Indian e-commerce platforms (such as Amazon.in, Flipkart, Croma, Reliance Digital, Vijay Sales, etc.).\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"1. DO NOT extract prices for accessories, cases, covers, chargers, or cables. Only extract the price of the actual product model itself.\n"
            f"2. DO NOT extract monthly EMI payment plans, subscription fees, or exchange discount values. Only extract the direct outright purchase price.\n"
            f"3. Ensure the links returned are valid, direct URLs to the products on their respective platforms.\n\n"
            f"Return the results as a JSON array of objects. Do not include markdown code block formatting, return ONLY the raw JSON list of objects.\n"
            f"Each object in the array must have these fields:\n"
            f"- 'platform': The name of the e-commerce store (e.g., 'Amazon', 'Flipkart', 'Croma', 'Reliance Digital').\n"
            f"- 'price': The current outright selling price of the product as a number (e.g. 54999).\n"
            f"- 'currency': 'INR'.\n"
            f"- 'link': The direct product link on that platform.\n"
        )
        
        logger.info(f"Querying Gemini 2.5 Flash with Search Grounding for product: {product_name}")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[{"google_search": {}}]
            )
        )
        
        content = response.text.strip()
        logger.info(f"Gemini Search Grounding raw output: {content}")
        
        # Clean markdown code blocks if present
        if "```" in content:
            import re
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
            if match:
                content = match.group(1).strip()
                
        # Parse the JSON response
        data = json.loads(content)
        if isinstance(data, list):
            validated_results = []
            for item in data:
                if "platform" in item and "price" in item:
                    # Clean price to float
                    try:
                        price_val = float(str(item["price"]).replace(",", ""))
                    except Exception:
                        continue
                    
                    platform_name = str(item["platform"])
                    query_encoded = urllib.parse.quote_plus(product_name)
                    default_link = f"https://www.google.com/search?q={platform_name}+{query_encoded}"
                    
                    validated_results.append({
                        "platform": platform_name,
                        "price": price_val,
                        "currency": str(item.get("currency", "INR")),
                        "link": str(item.get("link", default_link))
                    })
            return validated_results
    except Exception as e:
        logger.error(f"Error searching prices with Gemini Search Grounding: {e}")
    return []

def identify_product_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Sends an image to Gemini Vision to detect the product name.
    """
    client = get_client()
    if not client:
        logger.warning("GEMINI_API_KEY is missing or client initialization failed. Falling back to Mock Product Identification.")
        return "iPhone 15 Pro Max"
    
    try:
        prompt = (
            "You are an expert shopping assistant. Analyze the image and identify the exact product name, "
            "brand, and model. Return ONLY the product name. Example response format: 'iPhone 15 Pro Max' or "
            "'Sony WH-1000XM5'. Do not write markdown, code blocks, or additional explanation."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[
                types.Part.from_bytes(
                    data=image_bytes,
                    mime_type=mime_type,
                ),
                prompt
            ]
        )
        product_name = response.text.strip().replace("`", "").replace('"', '').replace("'", "")
        return product_name or "Unknown Product"
    except Exception as e:
        logger.error(f"Gemini image identification error: {e}")
        return "Detected Premium Product"

def generate_recommendation(product_name: str, results: List[Dict]) -> str:
    """
    Generates a helpful price comparison recommendation using Gemini.
    """
    if not results:
        return "No verified e-commerce listings found for this product."
    
    # Sort results by price
    sorted_results = sorted(results, key=lambda x: x["price"])
    lowest = sorted_results[0]
    highest = sorted_results[-1]
    savings = highest["price"] - lowest["price"]
    
    client = get_client()
    if not client:
        # Mock recommendation fallback
        if savings > 0:
            return (
                f"{lowest['platform']} currently offers the lowest available price at ₹{lowest['price']:,}. "
                f"Purchasing from {lowest['platform']} could save you approximately ₹{savings:,} "
                f"compared to buying from {highest['platform']} (₹{highest['price']:,})."
            )
        else:
            return f"The product is priced identically at ₹{lowest['price']:,} across all monitored platforms."

    try:
        prompt = (
            f"You are a price comparison assistant. Compare the prices for '{product_name}' "
            f"across these platforms: {json.dumps(results)}.\n"
            "Generate a highly professional, user-friendly purchase recommendation summary. "
            "Highlight the lowest price platform, exactly how much money can be saved, "
            "and any platform benefits (e.g. shipping speed, customer confidence). Keep the recommendation "
            "concise (2-3 sentences max) and format money figures with appropriate symbols (e.g. ₹ or $)."
        )
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"Gemini recommendation generation error: {e}")
        return (
            f"Best offer: {lowest['platform']} at ₹{lowest['price']:,}. "
            f"Save ₹{savings:,} relative to the highest price."
        )
