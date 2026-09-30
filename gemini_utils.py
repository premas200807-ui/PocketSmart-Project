"""
gemini_utils.py - AI recommendation service for PocketSmart AI

Handles:
  * Gemini configuration and model calls (text + image / multimodal)
  * Prompt building for the Home, Party and Jewelry planners
  * JSON extraction from AI responses
  * Budget calculation tables and budget-adherence checks
  * Shopping links for Indian platforms (Amazon, Flipkart, IKEA, Swiggy, Zomato, OYO ...)
  * Fallback / default recommendations when the AI is unavailable
"""
import json
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from PIL import Image

from models import HomeBudgetInput, JewelryBudgetInput, PartyBudgetInput

load_dotenv()

# ---------------------------------------------------------------------------
# Gemini configuration
# ---------------------------------------------------------------------------
API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

# The project document specifies Gemini 1.5 Flash. Google has since retired the
# 1.5 models, so we try the model from .env first and then newer Flash models.
PREFERRED_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MODEL_CANDIDATES = [m for m in dict.fromkeys(
    [PREFERRED_MODEL, "gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash", "gemini-1.5-flash"]
)]

client = None
_working_model: Optional[str] = None

if API_KEY:
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=API_KEY)
        print(f"[PocketSmart] Gemini configured. Preferred model: {PREFERRED_MODEL}")
    except Exception as exc:  # pragma: no cover
        print(f"[PocketSmart] Could not initialise Gemini client: {exc}")
        client = None
else:
    print("[PocketSmart] WARNING: No GOOGLE_API_KEY found in .env - running with fallback recommendations only.")


def ai_available() -> bool:
    return client is not None


def generate_with_gemini(contents: List[Any]) -> str:
    """Call Gemini with text (and optional PIL image) and return the raw text.
    Tries each candidate model until one works, then remembers it."""
    global _working_model
    if client is None:
        raise RuntimeError("Gemini API key not configured")

    from google.genai import types

    config = types.GenerateContentConfig(
        temperature=0.4,
        response_mime_type="application/json",
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    models_to_try = [_working_model] if _working_model else MODEL_CANDIDATES
    last_error: Optional[Exception] = None
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(model=model_name, contents=contents, config=config)
            if not response.text:
                raise ValueError("Empty response from Gemini")
            _working_model = model_name
            return response.text
        except Exception as exc:
            last_error = exc
            msg = str(exc).lower()
            # Only move to the next model if this one is missing / unsupported
            if "not found" in msg or "404" in msg or "not supported" in msg:
                continue
            break
    raise RuntimeError(f"Gemini request failed: {last_error}")


def extract_json_from_response(text: str) -> Dict[str, Any]:
    """Extract a JSON object from the model output (handles ```json fences and extra text)."""
    if not text:
        raise ValueError("Empty AI response")
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise ValueError("Could not parse JSON from AI response")


def usd_to_inr(amount_usd: float, exchange_rate: float = 83.0) -> float:
    """Convert USD amount to INR using the specified exchange rate"""
    return amount_usd * exchange_rate


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Shopping links
# ---------------------------------------------------------------------------
PLATFORM_URLS = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "ikea": "https://www.ikea.com/in/en/search/?q={q}",
    "pepperfry": "https://www.pepperfry.com/site_product/search?q={q}",
    "myntra": "https://www.myntra.com/{q}",
    "ajio": "https://www.ajio.com/search/?text={q}",
    "bigbasket": "https://www.bigbasket.com/ps/?q={q}",
    "swiggy": "https://www.swiggy.com/search?query={q}",
    "zomato": "https://www.zomato.com/search?q={q}",
    "bookmyshow": "https://in.bookmyshow.com/search?q={q}",
    "meesho": "https://www.meesho.com/search?q={q}",
    "google": "https://www.google.com/search?q={q}",
    "booking": "https://www.booking.com/searchresults.html?ss={q}",
    "makemytrip": "https://www.makemytrip.com/hotels/hotel-listing/?searchText={q}",
    "oyorooms": "https://www.oyorooms.com/search?location={q}",
    "nobroker": "https://www.nobroker.in/property/search?searchTerm={q}",
    "bluestone": "https://www.bluestone.com/search?search_query={q}",
    "tanishq": "https://www.tanishq.co.in/search?q={q}",
    "caratlane": "https://www.caratlane.com/search?q={q}",
    "melorra": "https://www.melorra.com/search?q={q}",
}


def build_links(search_terms: str, platforms: List[str]) -> Dict[str, str]:
    q = urllib.parse.quote_plus(search_terms)
    return {p: PLATFORM_URLS[p].format(q=q) for p in platforms if p in PLATFORM_URLS}


HOME_PLATFORMS = ["amazon", "flipkart", "ikea", "pepperfry", "myntra", "ajio"]

PARTY_CATEGORY_PLATFORMS = {
    "venue": ["google", "booking", "makemytrip", "oyorooms", "nobroker"],
    "catering": ["swiggy", "zomato"],
    "food": ["swiggy", "zomato", "bigbasket", "amazon", "flipkart"],
    "drinks": ["swiggy", "zomato", "bigbasket", "amazon", "flipkart"],
    "decoration": ["amazon", "flipkart", "meesho", "myntra"],
    "entertainment": ["bookmyshow", "amazon", "flipkart"],
    "gifts": ["amazon", "flipkart", "myntra", "meesho"],
    "photography": ["google", "amazon", "flipkart"],
    "music": ["amazon", "flipkart", "bookmyshow"],
    "games": ["amazon", "flipkart"],
    "accessories": ["amazon", "flipkart", "myntra", "meesho"],
    "transportation": ["makemytrip", "google"],
    "return_gifts": ["amazon", "flipkart", "myntra", "meesho"],
    "accommodation": ["oyorooms", "makemytrip", "booking"],
}
PARTY_DEFAULT_PLATFORMS = ["amazon", "flipkart", "google"]
VENUE_PLATFORMS = ["google", "booking", "makemytrip", "oyorooms", "nobroker"]
JEWELRY_PLATFORMS = ["amazon", "flipkart", "bluestone", "tanishq", "caratlane", "melorra", "meesho"]


# ---------------------------------------------------------------------------
# Post-processing: calculation table + budget check
# ---------------------------------------------------------------------------
def finalize_breakdown(result: Dict[str, Any], total_budget: float) -> Dict[str, Any]:
    """Recalculate totals from the actual items so the numbers are always correct,
    and flag the plan if the AI went over budget."""
    result["total_budget"] = round(total_budget, 2)
    table = []
    spent = 0.0
    for category in result.get("budget_breakdown", []) or []:
        items = category.get("items", []) or []
        cat_total = 0.0
        for item in items:
            price = _num(item.get("estimated_price"))
            qty = int(_num(item.get("quantity"), 1)) or 1
            item["estimated_price"] = round(price, 2)
            item["quantity"] = qty
            item["line_total"] = round(price * qty, 2)
            cat_total += price * qty
        category["allocation"] = round(_num(category.get("allocation"), cat_total) or cat_total, 2)
        spent += cat_total
        table.append({
            "category": category.get("category", "Misc"),
            "items_count": len(items),
            "total_cost": round(cat_total, 2),
            "percentage_of_budget": round(cat_total / total_budget * 100, 1) if total_budget else 0,
        })
    result["calculation_table"] = table
    result["total_spent"] = round(spent, 2)
    result["remaining_budget"] = round(total_budget - spent, 2)
    result["within_budget"] = spent <= total_budget
    result.setdefault("additional_suggestions", [])
    return result


# ---------------------------------------------------------------------------
# HOME INTERIOR PLANNER
# ---------------------------------------------------------------------------
def build_home_prompt(b: HomeBudgetInput) -> str:
    rooms = [r for r, flag in (("Living room", b.has_living_room), ("Kitchen", b.has_kitchen), ("Bedroom", b.has_bedroom)) if flag]
    return f"""
You are PocketSmart AI, an expert Indian home-interior budget planner.
I need interior design product recommendations for a home in India with a total budget of ₹{b.total_budget:.2f}.

Requirements:
- {b.num_lights} lights/lighting fixtures
- {b.num_fans} ceiling fans
- {b.num_furniture} furniture pieces
- {b.num_dining_tables} dining tables

Rooms to consider: {", ".join(rooms) if rooms else "Not specified"}
Additional requirements: {b.additional_requirements or "None"}

Please provide a detailed budget breakdown with product recommendations available in India.
Use Indian brands (e.g. Philips, Havells, Crompton, Wipro, IKEA, Nilkamal, Godrej Interio, Pepperfry, Urban Ladder) and realistic INR pricing.
Balance functionality, style and price. Skip categories whose quantity is 0.
"estimated_price" is the price of ONE unit; "quantity" is how many units. The sum of estimated_price x quantity
across all items MUST NOT exceed ₹{b.total_budget:.2f}.

Return ONLY JSON with this structure:
{{
  "total_budget": {b.total_budget:.2f},
  "budget_breakdown": [
    {{
      "category": "lighting",
      "allocation": 0.0,
      "items": [
        {{"name": "", "description": "", "brand": "", "estimated_price": 0.0, "quantity": 0, "search_terms": ""}}
      ]
    }}
  ],
  "remaining_budget": 0.0,
  "additional_suggestions": []
}}
Include short search terms for each item to find it on Amazon India, Flipkart and IKEA India.
"""


def fallback_home(b: HomeBudgetInput) -> Dict[str, Any]:
    """Rule-based default plan used when the AI is unavailable."""
    catalog = {
        "lighting": (b.num_lights, 700, [("LED Batten Light 20W", "Philips"), ("LED Ceiling Panel Light 15W", "Wipro"), ("Decorative Pendant Lamp", "Havells")]),
        "ceiling_fans": (b.num_fans, 2800, [("1200mm Ceiling Fan", "Crompton"), ("Energy-Saving BLDC Ceiling Fan", "Atomberg"), ("Decorative Ceiling Fan", "Havells")]),
        "furniture": (b.num_furniture, 9000, [("Engineered Wood Coffee Table", "Nilkamal"), ("3-Seater Fabric Sofa", "Wakefit"), ("Wooden Bookshelf", "IKEA")]),
        "dining_tables": (b.num_dining_tables, 16000, [("4-Seater Dining Table Set", "Nilkamal"), ("6-Seater Sheesham Dining Set", "Urban Ladder"), ("Glass Top Dining Set", "Godrej Interio")]),
    }
    base_cost = sum(q * p for q, p, _ in catalog.values())
    usable = b.total_budget * 0.85
    factor = min(1.6, usable / base_cost) if base_cost else 1
    tier = 0 if factor < 0.8 else (1 if factor < 1.25 else 2)

    breakdown = []
    for cat, (qty, price, options) in catalog.items():
        if qty <= 0:
            continue
        name, brand = options[tier]
        unit = max(99, round(price * factor, -1))
        breakdown.append({
            "category": cat,
            "allocation": unit * qty,
            "items": [{
                "name": name, "brand": brand,
                "description": f"{['Budget-friendly', 'Good value', 'Premium'][tier]} {cat.replace('_', ' ')} option from {brand}.",
                "estimated_price": unit, "quantity": qty,
                "search_terms": f"{brand} {name}",
            }],
        })
    spent = sum(c["allocation"] for c in breakdown)
    decor_budget = (b.total_budget - spent) * 0.6
    if decor_budget >= 500:
        rooms = [r for r, f in (("living room", b.has_living_room), ("kitchen", b.has_kitchen), ("bedroom", b.has_bedroom)) if f] or ["home"]
        breakdown.append({
            "category": "decor",
            "allocation": round(decor_budget, -1),
            "items": [{
                "name": f"Wall Art & Cushion Set for {rooms[0].title()}", "brand": "Home Centre",
                "description": "Adds colour and personality without major spend.",
                "estimated_price": round(decor_budget, -1), "quantity": 1,
                "search_terms": f"{rooms[0]} wall decor cushion set",
            }],
        })
    return {
        "total_budget": b.total_budget,
        "budget_breakdown": breakdown,
        "additional_suggestions": [
            "Compare prices across Amazon, Flipkart and IKEA before buying - sale prices vary a lot.",
            "BLDC fans cost more upfront but save on electricity bills.",
            "Keep 10-15% of the budget aside for installation and delivery charges.",
        ],
    }


def get_home_recommendations(budget_input: HomeBudgetInput) -> Dict[str, Any]:
    """Generate home interior recommendations within budget in INR for Indian market"""
    source, note = "gemini", None
    try:
        result = extract_json_from_response(generate_with_gemini([build_home_prompt(budget_input)]))
        if not result.get("budget_breakdown"):
            raise ValueError("AI returned no recommendations")
    except Exception as exc:
        print(f"[PocketSmart] Home planner fallback: {exc}")
        result, source, note = fallback_home(budget_input), "fallback", str(exc)

    result = finalize_breakdown(result, budget_input.total_budget)
    for category in result.get("budget_breakdown", []):
        for item in category.get("items", []):
            terms = item.get("search_terms") or item.get("name", "")
            if terms:
                item["shopping_links"] = build_links(terms, HOME_PLATFORMS)
    result["source"] = source
    if note:
        result["note"] = "AI service unavailable - showing default recommendations."
    return result


# ---------------------------------------------------------------------------
# PARTY PLANNER
# ---------------------------------------------------------------------------
def build_party_prompt(b: PartyBudgetInput) -> str:
    return f"""
You are PocketSmart AI, an expert Indian event and party budget planner.
I need party planning recommendations for India with a total budget of ₹{b.total_budget:.2f}.

Party details:
- Type: {b.party_type}
- Number of guests: {b.num_guests}
- Venue type: {b.venue_type or "Not specified"}
- Catering needed: {"Yes" if b.needs_catering else "No"}
- Decoration needed: {"Yes" if b.needs_decoration else "No"}
- Entertainment needed: {"Yes" if b.needs_entertainment else "No"}

Additional requirements: {b.additional_requirements or "None"}

Allocate the budget proportionally across venue, catering, decoration and entertainment (only those needed),
tailored to the event type. Use Indian vendors/services (Swiggy, Zomato, OYO, BookMyShow, Amazon, Flipkart) and realistic INR prices.
"estimated_price" is the price of ONE unit; "quantity" is how many units. The sum of estimated_price x quantity
MUST NOT exceed ₹{b.total_budget:.2f}. Use category names such as: venue, catering, food, drinks, decoration,
entertainment, photography, return_gifts, contingency.

Return ONLY JSON with this structure:
{{
  "total_budget": {b.total_budget:.2f},
  "budget_breakdown": [
    {{
      "category": "venue",
      "allocation": 0.0,
      "items": [
        {{"name": "", "description": "", "estimated_price": 0.0, "quantity": 1, "search_terms": ""}}
      ]
    }}
  ],
  "venue_suggestions": [
    {{"name": "", "type": "", "capacity": 0, "estimated_cost": 0.0, "search_terms": ""}}
  ],
  "remaining_budget": 0.0,
  "additional_suggestions": []
}}
Provide search terms suitable for Indian websites such as BookMyShow, Swiggy, Zomato, OYO, Flipkart, etc.
"""


def fallback_party(b: PartyBudgetInput) -> Dict[str, Any]:
    weights = {"venue": 30, "catering": 40 if b.needs_catering else 0,
               "decoration": 15 if b.needs_decoration else 0,
               "entertainment": 10 if b.needs_entertainment else 0, "contingency": 5}
    total_w = sum(weights.values())
    alloc = {k: b.total_budget * w / total_w for k, w in weights.items() if w}
    ptype = b.party_type.lower()
    g = b.num_guests
    breakdown = []
    if "venue" in alloc:
        breakdown.append({"category": "venue", "allocation": alloc["venue"], "items": [{
            "name": f"{(b.venue_type or 'Banquet hall').title()} booking", "quantity": 1,
            "description": f"Space for about {g} guests for a {ptype} event.",
            "estimated_price": round(alloc["venue"], -1), "search_terms": f"{b.venue_type or 'party hall'} for {g} guests"}]})
    if "catering" in alloc:
        plate = max(10, int(alloc["catering"] / g))
        breakdown.append({"category": "catering", "allocation": alloc["catering"], "items": [{
            "name": "Veg + Non-veg buffet (per plate)", "quantity": g,
            "description": "Starters, main course and dessert from a local caterer.",
            "estimated_price": plate, "search_terms": f"{ptype} catering per plate"}]})
    if "decoration" in alloc:
        breakdown.append({"category": "decoration", "allocation": alloc["decoration"], "items": [
            {"name": f"{ptype.title()} theme decoration kit", "quantity": 1, "description": "Balloons, banners, backdrop and lights.",
             "estimated_price": round(alloc["decoration"] * 0.6, -1), "search_terms": f"{ptype} decoration kit"},
            {"name": "LED fairy lights", "quantity": 2, "description": "Warm lighting for ambience.",
             "estimated_price": round(alloc["decoration"] * 0.2, -1), "search_terms": "LED fairy lights 10m"}]})
    if "entertainment" in alloc:
        breakdown.append({"category": "entertainment", "allocation": alloc["entertainment"], "items": [{
            "name": "DJ / music system rental", "quantity": 1, "description": "Sound system with playlist for the event.",
            "estimated_price": round(alloc["entertainment"], -1), "search_terms": f"DJ for {ptype} party"}]})
    breakdown.append({"category": "contingency", "allocation": alloc["contingency"], "items": [{
        "name": "Buffer for unexpected costs", "quantity": 1, "description": "Transport, tips and last-minute purchases.",
        "estimated_price": round(alloc["contingency"], -1), "search_terms": ""}]})
    return {
        "total_budget": b.total_budget,
        "budget_breakdown": breakdown,
        "venue_suggestions": [
            {"name": f"Community / party hall near you", "type": b.venue_type or "Banquet hall", "capacity": g,
             "estimated_cost": round(alloc.get("venue", 0), -1), "search_terms": f"party hall for {g} guests"},
            {"name": "Hotel banquet (OYO / budget hotels)", "type": "Hotel", "capacity": g,
             "estimated_cost": round(alloc.get("venue", 0), -1), "search_terms": f"hotel banquet {ptype}"},
        ],
        "additional_suggestions": [
            "Book the venue and caterer at least 2-3 weeks early for better rates.",
            "Order bulk snacks and drinks from BigBasket to reduce catering cost.",
            "Confirm the final guest count 3 days before to avoid food wastage.",
        ],
    }


def get_party_recommendations(budget_input: PartyBudgetInput) -> Dict[str, Any]:
    """Generate party planning recommendations within budget in INR for Indian market"""
    source, note = "gemini", None
    try:
        result = extract_json_from_response(generate_with_gemini([build_party_prompt(budget_input)]))
        if not result.get("budget_breakdown"):
            raise ValueError("AI returned no recommendations")
    except Exception as exc:
        print(f"[PocketSmart] Party planner fallback: {exc}")
        result, source, note = fallback_party(budget_input), "fallback", str(exc)

    result = finalize_breakdown(result, budget_input.total_budget)
    result["calculation_table_inr"] = result["calculation_table"]

    for category in result.get("budget_breakdown", []):
        cat_name = str(category.get("category", "")).lower().replace(" ", "_")
        relevant_platforms = PARTY_CATEGORY_PLATFORMS.get(cat_name, PARTY_DEFAULT_PLATFORMS)
        for item in category.get("items", []):
            terms = item.get("search_terms", "")
            if terms:
                item["shopping_links"] = build_links(terms, relevant_platforms)

    for venue in result.get("venue_suggestions", []) or []:
        venue["estimated_cost"] = round(_num(venue.get("estimated_cost")), 2)
        terms = venue.get("search_terms", "")
        if terms:
            venue["search_links"] = build_links(terms, VENUE_PLATFORMS)

    result["source"] = source
    if note:
        result["note"] = "AI service unavailable - showing default recommendations."
    return result


# ---------------------------------------------------------------------------
# JEWELRY PLANNER (multimodal: text + optional outfit image)
# ---------------------------------------------------------------------------
JEWELRY_JSON = """
{
  "outfit_analysis": {"colors": [], "style": "", "formality": ""},
  "total_budget": 0.0,
  "jewelry_recommendations": [
    {"item_type": "", "description": "", "style": "", "material": "", "estimated_price": 0.0, "search_terms": ""}
  ],
  "remaining_budget": 0.0,
  "styling_tips": []
}
"""


def build_jewelry_prompt(b: JewelryBudgetInput, has_image: bool) -> str:
    base = f"""
You are PocketSmart AI, an expert Indian jewelry stylist and budget planner.
I need jewelry recommendations for India with a total budget of ₹{b.total_budget:.2f}.

Occasion: {b.occasion}
Preferences: {b.preferences or "Not specified"}
Provide only India-relevant styles, brands (Tanishq, CaratLane, BlueStone, Melorra, Kushal's, Zaveri Pearls, etc.),
availability, and price ranges in INR. The sum of all estimated_price values MUST NOT exceed ₹{b.total_budget:.2f}.
"""
    if has_image:
        base += """
An image of the outfit is uploaded. First analyse the outfit (main colours, style, formality), then suggest
jewelry that complements it, considering colour coordination, design and occasion appropriateness.
"""
    else:
        base += "\nNo outfit image was provided. Set outfit_analysis to null.\n"
    return base + "\nReturn ONLY JSON with this structure:\n" + JEWELRY_JSON + "\nInclude Indian-friendly search terms for shopping."


def fallback_jewelry(b: JewelryBudgetInput) -> Dict[str, Any]:
    occ = b.occasion.lower()
    festive = any(w in occ for w in ("wedding", "festival", "diwali", "engagement", "reception", "pooja"))
    budget = b.total_budget
    material = "gold-plated / kundan" if festive else "sterling silver / fashion"
    if budget >= 60000:
        material = "22K gold" if festive else "18K gold / diamond"
    plan = [("Necklace", 0.45), ("Earrings", 0.25), ("Bangles" if festive else "Bracelet", 0.2)]
    recs = [{
        "item_type": it,
        "description": f"{material.title()} {it.lower()} suited for {b.occasion}.",
        "style": "Traditional" if festive else "Contemporary",
        "material": material,
        "estimated_price": round(budget * share, -1),
        "search_terms": f"{material.split('/')[0].strip()} {it.lower()} for {b.occasion}",
    } for it, share in plan]
    return {
        "outfit_analysis": None,
        "total_budget": budget,
        "jewelry_recommendations": recs,
        "styling_tips": [
            "Pick one statement piece and keep the rest minimal.",
            "Match metal tone to your outfit's embroidery (gold for warm tones, silver for cool tones).",
            "Check BIS hallmark when buying gold jewelry.",
        ],
    }


def get_jewelry_recommendations(budget_input: JewelryBudgetInput, image_path: Optional[str] = None) -> Dict[str, Any]:
    """Generate jewelry recommendations based on uploaded dress and budget in INR (India-specific)"""
    source, note = "gemini", None
    try:
        prompt = build_jewelry_prompt(budget_input, bool(image_path))
        contents: List[Any] = [prompt]
        if image_path:
            img = Image.open(image_path)
            img.thumbnail((1024, 1024))
            contents.append(img)
        result = extract_json_from_response(generate_with_gemini(contents))
        if not result.get("jewelry_recommendations"):
            raise ValueError("AI returned no recommendations")
    except Exception as exc:
        print(f"[PocketSmart] Jewelry planner fallback: {exc}")
        result, source, note = fallback_jewelry(budget_input), "fallback", str(exc)

    total = budget_input.total_budget
    spent = 0.0
    for item in result.get("jewelry_recommendations", []):
        item["estimated_price"] = round(_num(item.get("estimated_price")), 2)
        spent += item["estimated_price"]
        terms = item.get("search_terms") or item.get("item_type", "")
        if terms:
            item["shopping_links"] = build_links(terms, JEWELRY_PLATFORMS)
    result["total_budget"] = total
    result["total_spent"] = round(spent, 2)
    result["remaining_budget"] = round(total - spent, 2)
    result["within_budget"] = spent <= total
    result.setdefault("styling_tips", [])
    result["source"] = source
    if note:
        result["note"] = "AI service unavailable - showing default recommendations."
    return result
