import os
import re
import json
import logging
import requests
from datetime import datetime
import concurrent.futures
from typing import List, Dict, Tuple

logger = logging.getLogger("search_engine")

class SearchEngine:
    APPROVED_DOMAINS = {
        # High Priority
        "amazon.in": "Amazon",
        "flipkart.com": "Flipkart",
        "croma.com": "Croma",
        "reliancedigital.in": "Reliance Digital",
        "vijaysales.com": "Vijay Sales",
        "tatacliq.com": "Tata Cliq",
        "jiomart.com": "JioMart",
        # Medium Priority
        "apple.com": "Apple Store",
        "samsung.com": "Samsung Store",
        "oneplus.in": "OnePlus Store",
        "mi.com": "Mi Store",
        "boat-lifestyle.com": "boAt Store",
        "hp.com": "HP Store",
        "dell.com": "Dell Store",
        "lenovo.com": "Lenovo Store"
    }

    DOMAIN_SCORES = {
        "amazon.in": 100,
        "flipkart.com": 100,
        "croma.com": 100,
        "reliancedigital.in": 100,
        "vijaysales.com": 100,
        "tatacliq.com": 100,
        "jiomart.com": 100,
        "apple.com": 90,
        "samsung.com": 90,
        "oneplus.in": 90,
        "mi.com": 90,
        "boat-lifestyle.com": 90,
        "hp.com": 90,
        "dell.com": 90,
        "lenovo.com": 90
    }

    def __init__(self):
        self.gemini_client = self._get_gemini_client()
        self.tavily_key = os.environ.get("TAVILY_API_KEY")

    def _get_gemini_client(self):
        try:
            from backend.services.ai_service import get_client
            return get_client()
        except Exception as e:
            logger.error(f"Failed to fetch Gemini client: {e}")
            return None

    def parse_product_query(self, raw_query: str) -> Dict:
        """
        Product Understanding Layer: Extracts brand, product name, variant, 
        and expected price bounds for validation.
        """
        if self.gemini_client:
            try:
                prompt = (
                    f"Analyze the user's shopping search query: '{raw_query}'.\n"
                    "Extract structured product information in JSON format. Do not use markdown tags, code blocks, or backticks, return ONLY the raw JSON.\n"
                    "Extract the following keys:\n"
                    "- 'brand': Brand name (e.g. Apple, Samsung, Sony)\n"
                    "- 'product': Main product model name (e.g. iPhone 15, Galaxy S24 Ultra, WH-1000XM5)\n"
                    "- 'variant': Storage, RAM, or specific dimensions (e.g. 128GB, 256GB, 8GB RAM)\n"
                    "- 'min_price': Estimate the lowest realistic retail price in India (INR) as an integer (e.g. 60000)\n"
                    "- 'max_price': Estimate the highest realistic retail price in India (INR) as an integer (e.g. 150000)\n"
                )
                response = self.gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                data = json.loads(response.text.strip().replace("```json", "").replace("```", ""))
                
                # Validation of keys
                brand = str(data.get("brand") or "").strip()
                product = str(data.get("product") or "").strip()
                variant = str(data.get("variant") or "").strip()
                
                try:
                    min_price = int(float(data.get("min_price", 100)))
                except (ValueError, TypeError):
                    min_price = 100
                
                try:
                    max_price = int(float(data.get("max_price", 10000000)))
                except (ValueError, TypeError):
                    max_price = 10000000

                return {
                    "brand": brand,
                    "product": product,
                    "variant": variant,
                    "min_price": min_price,
                    "max_price": max_price
                }
            except Exception as e:
                logger.error(f"Gemini Product Parsing failed, using fallback: {e}")

        # Fallback parsing
        return self._fallback_product_parsing(raw_query)

    def _fallback_product_parsing(self, raw_query: str) -> Dict:
        brands = ["apple", "samsung", "sony", "oneplus", "google", "xiaomi", "redmi", "realme", "boat"]
        brand = ""
        lower_query = raw_query.lower()
        for b in brands:
            if b in lower_query:
                brand = b.capitalize()
                break

        variant_match = re.search(r'\b\d+\s*(?:gb|tb)\b', lower_query)
        variant = variant_match.group(0).upper() if variant_match else ""

        # Default fallback bounds based on category keywords
        min_price = 500
        max_price = 300000
        
        if any(k in lower_query for k in ["iphone", "macbook", "ipad", "galaxy s", "ultra", "pixel pro", "fold", "laptop", "loq", "rtx", "gtx", "lenovo", "gaming"]):
            min_price = 25000
        elif any(k in lower_query for k in ["wh-1000", "airpods pro", "bose"]):
            min_price = 12000
        elif any(k in lower_query for k in ["tv", "television", "monitor"]):
            min_price = 8000
        elif any(k in lower_query for k in ["watch", "smartwatch"]):
            min_price = 2000
        elif any(k in lower_query for k in ["phone", "oneplus", "xiaomi", "realme"]):
            min_price = 6000

        return {
            "brand": brand,
            "product": raw_query,
            "variant": variant,
            "min_price": min_price,
            "max_price": max_price
        }

    def normalize_text(self, t: str) -> str:
        t = t.lower()
        # Insert space between digits and letters (e.g. 256gb -> 256 gb, wh-1000xm5 -> wh-1000 xm 5)
        t = re.sub(r'(\d+)([a-z]+)', r'\1 \2', t)
        t = re.sub(r'([a-z]+)(\d+)', r'\1 \2', t)
        # Replace non-alphanumeric with spaces
        t = re.sub(r'[^a-z0-9\s]', ' ', t)
        # Normalize whitespace
        return re.sub(r'\s+', ' ', t).strip()

    def get_core_product_words(self, parsed: Dict) -> set:
        brand = parsed.get("brand", "").lower()
        product = parsed.get("product", "").lower()
        variant = parsed.get("variant", "").lower()
        
        prod_norm = self.normalize_text(product)
        words = set(prod_norm.split())
        
        # Remove brand
        if brand in words:
            words.remove(brand)
            
        # Remove variant words
        var_norm = self.normalize_text(variant)
        for w in var_norm.split():
            if w in words:
                words.remove(w)
                
        # Remove colors
        colors = {"black", "white", "silver", "gold", "gray", "grey", "blue", "red", "green", "yellow", "purple", "pink", "orange", "cosmic", "titanium", "starlight", "midnight"}
        words = words - colors
        
        return words

    def generate_queries(self, parsed: Dict) -> List[str]:
        """
        Intelligent Query Generation: Generates highly targeted queries for shopping search.
        """
        brand = parsed.get("brand", "").strip()
        product = parsed.get("product", "").strip()
        variant = parsed.get("variant", "").strip()
        
        if brand and product.lower().startswith(brand.lower()):
            product_str = f"{product}".strip()
        else:
            product_str = f"{brand} {product}".strip()
            
        if variant and variant.lower() not in product_str.lower():
            product_str = f"{product_str} {variant}".strip()
            
        product_str = re.sub(r'\s+', ' ', product_str)
        
        queries = [
            f"{product_str} price on Amazon Flipkart Croma",
            f"{product_str} price on Reliance Digital Vijay Sales Tata Cliq JioMart",
            f"{product_str} buy online official store price in India"
        ]
        return queries

    def execute_tavily_search(self, queries: List[str]) -> List[Dict]:
        """
        Executes parallelized search queries across Tavily.
        """
        if not self.tavily_key:
            logger.warning("No TAVILY_API_KEY set. Cannot run Tavily search.")
            return []

        search_results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(queries)) as executor:
            future_to_query = {
                executor.submit(self._tavily_single_search, query): query 
                for query in queries
            }
            for future in concurrent.futures.as_completed(future_to_query):
                res = future.result()
                if res:
                    search_results.extend(res)
        return search_results

    def _tavily_single_search(self, query: str) -> List[Dict]:
        url = "https://api.tavily.com/search"
        payload = {
            "api_key": self.tavily_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 4
        }
        try:
            response = requests.post(url, json=payload, timeout=6)
            if response.status_code == 200:
                return response.json().get("results", [])
        except Exception as e:
            logger.error(f"Tavily search API error: {e}")
        return []

    def identify_platform(self, url: str, title: str) -> str:
        """
        Identifies if a result maps to one of our approved domains.
        """
        from urllib.parse import urlparse
        try:
            netloc = urlparse(url).netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            
            for domain, name in self.APPROVED_DOMAINS.items():
                if netloc == domain or netloc.endswith("." + domain):
                    return name
        except Exception:
            pass
        return ""

    def get_domain_score(self, url: str) -> int:
        """
        Extracts domain and matches it against domain scoring rules.
        """
        from urllib.parse import urlparse
        try:
            netloc = urlparse(url).netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
                
            for domain, score in self.DOMAIN_SCORES.items():
                if netloc == domain or netloc.endswith("." + domain):
                    return score
        except Exception:
            pass
        return 50 # Unknown Store

    def validate_product_page(self, url: str, title: str, snippet: str) -> bool:
        """
        Verifies that the URL appears to be a product page and not review/news/buying-guide.
        """
        url_lower = url.lower()
        title_lower = title.lower()
        snippet_lower = snippet.lower()
        
        # Blocked patterns in URL path or query
        blocked_url_patterns = [
            "/reviews/", "/review/", "/news/", "/blog/", "/buying-guide/", "/article/", 
            "/best-", "/top-", "/versus/", "/vs/", "comparison", "compare", "forums", 
            "forum", "topic", "discussion", "threads", "specifications", "spec-sheet"
        ]
        if any(pattern in url_lower for pattern in blocked_url_patterns):
            logger.info(f"URL {url} rejected: matched blocked URL pattern")
            return False
            
        # Blocked patterns in Title or Snippet
        blocked_content_patterns = [
            "review of", "hands-on", "unboxing", "first look", "buying guide", 
            "best headphones", "best phones", "best laptops", "top 10", "top 5", 
            "specifications", "spec sheet", "versus", " vs ", "how to buy", "released",
            "launching", "launched", "announced", "announcement", "first impressions"
        ]
        if any(pattern in title_lower or pattern in snippet_lower for pattern in blocked_content_patterns):
            logger.info(f"URL {url} rejected: matched blocked content pattern in title/snippet")
            return False
            
        return True

    def calculate_confidence(self, parsed: Dict, title: str, snippet: str) -> int:
        """
        Product Matching Engine: Computes a matching confidence score.
        """
        brand = parsed.get("brand", "").strip()
        product = parsed.get("product", "").strip()
        variant = parsed.get("variant", "").strip()
        
        if brand and product.lower().startswith(brand.lower()):
            target_product = f"{product} {variant}".strip()
        else:
            target_product = f"{brand} {product} {variant}".strip()
        target_product = re.sub(r'\s+', ' ', target_product)
        
        # accessory filtration
        lower_title = title.lower()
        accessory_keywords = ["case", "cover", "tempered glass", "adapter", "guard", "screen protector", "sleeve", "cable", "strap"]
        for ack in accessory_keywords:
            if ack in lower_title and ack not in target_product.lower():
                return 0 # Definitely an accessory, mismatch!

        if self.gemini_client:
            try:
                prompt = (
                    f"Compare the target product: '{target_product}' with this search listing title: '{title}' and description: '{snippet}'.\n"
                    "Evaluate if this listing matches the exact product the user is looking for.\n"
                    "Assign a confidence score strictly from the scale:\n"
                    "- 100: Exact match (identical model, series, brand)\n"
                    "- 80: Likely match (same item, but mismatch in color, package format, or color description)\n"
                    "- 50: Partial match (same brand, but different size, generation, or storage variant)\n"
                    "- 0: Mismatch (different model, accessory only, case, cover, charger, cable, or incorrect brand)\n\n"
                    "Return ONLY the raw integer confidence score. Do not write markdown, code blocks, or explanations."
                )
                response = self.gemini_client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt
                )
                score_str = response.text.strip().replace("`","")
                score_match = re.search(r'\d+', score_str)
                if score_match:
                    score = int(score_match.group(0))
                    if score in [100, 80, 50, 0]:
                        return 98 if score == 100 else score
                    return 98 if score >= 90 else (80 if score >= 75 else (50 if score >= 45 else 0))
            except Exception as e:
                logger.error(f"Gemini matching engine error: {e}")

        # Fallback keyword match
        return self._fallback_confidence(parsed, title)

    def _fallback_confidence(self, parsed: Dict, title: str) -> int:
        title_norm = self.normalize_text(title)
        title_words = set(title_norm.split())
        
        brand_lower = parsed.get("brand", "").lower()
        if brand_lower and brand_lower not in title_words:
            if not any(brand_lower in w for w in title_words):
                return 0

        # Check sub-model modifiers using word boundaries
        modifiers = ["ultra", "pro", "max", "plus", "fe", "mini", "lite"]
        prod_lower = parsed.get("product", "").lower()
        for mod in modifiers:
            has_prod = bool(re.search(rf'\b{mod}\b', prod_lower))
            has_title = bool(re.search(rf'\b{mod}\b', title_norm))
            if has_prod != has_title:
                return 0

        # Check exact numbers
        target_numbers = set(re.findall(r'\d+', prod_lower))
        title_numbers = set(re.findall(r'\d+', title_norm))
        if target_numbers and not target_numbers.issubset(title_numbers):
            return 0

        # Extract core words
        core_words = self.get_core_product_words(parsed)
        if not core_words:
            return 0
            
        # Core words must be present in the title
        if not core_words.issubset(title_words):
            matched_cores = 0
            for cw in core_words:
                if cw in title_norm:
                    matched_cores += 1
            if matched_cores < len(core_words):
                return 0

        # If brand, modifiers, numbers, and core words match, check variant
        variant_lower = parsed.get("variant", "").lower()
        if variant_lower:
            variant_norm = self.normalize_text(variant_lower)
            variant_words = set(variant_norm.split())
            if variant_words.issubset(title_words):
                return 98
            return 80
            
        return 98

    def extract_price_candidates(self, text: str) -> List[int]:
        """
        Price Extraction Engine: Extracts and normalizes pricing candidates,
        stripping out EMI and per-month plans.
        """
        # Clean text by removing EMI phrases
        clean_text = re.sub(
            r'(?:no cost\s+)?emi\s*(?:starts?\s+(?:at|from)|starting\s+at|Rs\.?|₹)?\s*[\d,]+(?:\.\d+)?(?:\s*/\s*(?:month|mo)\b|\s*p\.m\.?|\s*pm)?',
            '', text, flags=re.IGNORECASE
        )
        clean_text = re.sub(
            r'[\d,]+(?:\.\d+)?\s*(?:per\s+(?:month|mo)|/(?:month|mo)|pm|p\.m\.)',
            '', clean_text, flags=re.IGNORECASE
        )

        # Support both Indian Lakhs (2-digit grouping) and Western formatting
        patterns = [
            r'(?:₹|Rs\.?|INR)\s*(\d{1,3}(?:,\d{2,3})*(?:\.\d+)?|\d+)',
            r'\b(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?)\b'
        ]
        
        extracted = []
        for pattern in patterns:
            matches = re.findall(pattern, clean_text, re.IGNORECASE)
            for m in matches:
                clean_p = m.replace(",", "")
                if "." in clean_p:
                    clean_p = clean_p.split(".")[0]
                try:
                    val = int(clean_p)
                    if val > 0:
                        extracted.append(val)
                except ValueError:
                    continue
        
        return list(set(extracted))

    def validate_price(self, price: int, parsed: Dict) -> bool:
        """
        Price Validation Engine: Confirms price is positive and realistic.
        """
        if price <= 0:
            return False
        # Apply a safety margin to the LLM-estimated boundaries
        # Allow price to be as low as 60% of the estimated min_price (40% discount/price drop)
        # Allow price to be as high as 150% of the estimated max_price (higher storage/variant)
        min_allowed = int(parsed["min_price"] * 0.6)
        max_allowed = int(parsed["max_price"] * 1.5)
        
        if price < min_allowed or price > max_allowed:
            logger.info(f"Price {price} rejected. Outside realistic range: {min_allowed} - {max_allowed} (parsed: {parsed['min_price']} - {parsed['max_price']})")
            return False
        return True

    def process_search(self, raw_query: str) -> Tuple[str, List[Dict], int]:
        """
        Full Search Engine Execution Pipeline: Runs understanding, query generation, 
        tavily search, extraction, matching, validation, deduplication and sorting.
        """
        logger.info(f"Initiating search pipeline for raw query: {raw_query}")
        
        # 1. Product Understanding
        parsed = self.parse_product_query(raw_query)
        brand = parsed.get("brand", "").strip()
        product = parsed.get("product", "").strip()
        variant = parsed.get("variant", "").strip()
        
        if brand and product.lower().startswith(brand.lower()):
            product_name = f"{product}".strip()
        else:
            product_name = f"{brand} {product}".strip()
            
        if variant and variant.lower() not in product_name.lower():
            product_name = f"{product_name} {variant}".strip()
            
        product_name = re.sub(r'\s+', ' ', product_name)
        logger.info(f"Parsed product name: {product_name}")

        # 2. Query Generation
        queries = self.generate_queries(parsed)
        logger.info(f"Generated queries: {queries}")

        # 3. Search Executions
        search_results = self.execute_tavily_search(queries)
        logger.info(f"Retrieved {len(search_results)} raw search results from Tavily")

        # 4. Extract offers using Gemini reasoning
        raw_offers = self.extract_prices_from_results_with_gemini(product_name, search_results)
        
        # Fallback to regex extraction if Gemini returns no results
        if not raw_offers:
            logger.info("Gemini extraction returned no offers. Falling back to regex parser...")
            for res in search_results:
                title = res.get("title", "")
                url = res.get("url", "")
                snippet = res.get("content", "")

                # Identify platform
                platform = self.identify_platform(url, title)
                if not platform:
                    continue

                # Enforce Domain Scoring (Only results above 80 may be shown)
                score = self.get_domain_score(url)
                if score <= 80:
                    logger.info(f"URL {url} discarded: domain score {score} is <= 80")
                    continue

                # Validate URL is a product/store page and not a review/news/buying-guide
                if not self.validate_product_page(url, title, snippet):
                    continue

                # Extract price candidates
                price_candidates = self.extract_price_candidates(f"{title} {snippet}")
                valid_prices = [p for p in price_candidates if self.validate_price(p, parsed)]
                if not valid_prices:
                    continue

                # Select the correct product retail price
                price = min(valid_prices)

                # Pre-filter using fast fallback confidence to prevent hitting Gemini rate limits
                fallback_conf = self._fallback_confidence(parsed, title)
                if fallback_conf < 50:
                    continue

                # Calculate confidence using Gemini (or fallback if it fails / is rate-limited)
                confidence = self.calculate_confidence(parsed, title, snippet)
                if confidence < 50: # Threshold check: Reject below 50
                    continue

                raw_offers.append({
                    "platform": platform,
                    "price": float(price),
                    "currency": "INR",
                    "link": url,
                    "confidence": confidence
                })

        # 5. Deduplicate Listings (Keep best match per platform)
        deduplicated = {}
        for offer in raw_offers:
            plat = offer["platform"]
            if plat not in deduplicated:
                deduplicated[plat] = offer
            else:
                existing = deduplicated[plat]
                if offer["confidence"] > existing["confidence"]:
                    deduplicated[plat] = offer
                elif offer["confidence"] == existing["confidence"] and offer["price"] < existing["price"]:
                    deduplicated[plat] = offer

        verified_offers = list(deduplicated.values())

        # 6. Sorting & Ranking (Lowest Price First)
        verified_offers = sorted(verified_offers, key=lambda x: x["price"])
        
        # Calculate search confidence score
        overall_confidence = 0
        if verified_offers:
            overall_confidence = int(sum(o["confidence"] for o in verified_offers) / len(verified_offers))

        return product_name, verified_offers, overall_confidence

    def extract_prices_from_results_with_gemini(self, product_name: str, search_results: List[Dict]) -> List[Dict]:
        """
        Uses Gemini to extract factual product prices, platforms, and URLs from search results.
        """
        if not self.gemini_client or not search_results:
            return []

        # Prepare search results context for the prompt
        context_items = []
        for idx, res in enumerate(search_results[:12]):
            context_items.append(
                f"Result #{idx+1}:\n"
                f"Title: {res.get('title', '')}\n"
                f"URL: {res.get('url', '')}\n"
                f"Snippet: {res.get('content', '')}\n"
            )
        context_text = "\n".join(context_items)

        prompt = (
            f"You are a price comparison data extractor. Your job is to extract direct retail prices and URLs for the product: '{product_name}' "
            f"from the search engine results provided below.\n\n"
            f"SEARCH RESULTS:\n"
            f"{context_text}\n\n"
            f"EXTRACTION RULES:\n"
            f"1. Only identify offers from approved major platforms (e.g. Amazon, Flipkart, Croma, Reliance Digital, Vijay Sales, Tata Cliq, JioMart, or official brand stores like Apple, Samsung, Sony).\n"
            f"2. DO NOT extract prices of accessories (like cases, covers, chargers, screen guards, cables). ONLY extract prices for the actual product '{product_name}'.\n"
            f"3. DO NOT extract monthly EMI payment plans, monthly subscription rates, or exchange discount values. Extract ONLY the full outright purchase price.\n"
            f"4. Ignore listings that do not contain a clear, specific price for the actual product.\n"
            f"5. Return the results as a JSON array of objects. Do not include markdown code block formatting or any extra text, return ONLY the raw JSON list of objects.\n"
            f"Each object in the array must have the following fields:\n"
            f"- 'platform': The e-commerce store name (e.g. 'Amazon', 'Flipkart', 'Croma', 'Reliance Digital')\n"
            f"- 'price': The retail price of the product as a number (e.g. 54999)\n"
            f"- 'currency': 'INR'\n"
            f"- 'link': The exact URL corresponding to that listing\n"
        )

        try:
            logger.info(f"Querying Gemini 2.5 Flash to extract prices from Tavily results for: {product_name}")
            response = self.gemini_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )
            content = response.text.strip()
            logger.info(f"Gemini Tavily extraction raw output: {content}")
            
            # Clean markdown code blocks if present
            if "```" in content:
                import re
                match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', content)
                if match:
                    content = match.group(1).strip()
            
            data = json.loads(content)
            if isinstance(data, list):
                extracted = []
                for item in data:
                    if "platform" in item and "price" in item and "link" in item:
                        try:
                            price_val = float(str(item["price"]).replace(",", ""))
                            if price_val > 0:
                                extracted.append({
                                    "platform": str(item["platform"]),
                                    "price": price_val,
                                    "currency": str(item.get("currency", "INR")),
                                    "link": str(item["link"]),
                                    "confidence": 95
                                })
                        except Exception:
                            continue
                return extracted
        except Exception as e:
            logger.error(f"Gemini price extraction from search results failed: {e}")
        return []
