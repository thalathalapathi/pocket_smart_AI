import os
import json
import re
import urllib.parse
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from PIL import Image
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Gemini AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Warning: Failed to configure Gemini with provided key: {e}")

# Supported model names
PRIMARY_MODEL = "gemini-1.5-flash"
FALLBACK_MODEL = "gemini-2.5-flash"

def get_gemini_model(model_name: str = PRIMARY_MODEL):
    """Instantiate a Gemini model instance safely with dynamic API key reload."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if api_key:
        try:
            genai.configure(api_key=api_key)
        except Exception as e:
            print(f"Warning: Failed to configure Gemini with provided key: {e}")
    try:
        return genai.GenerativeModel(model_name)
    except Exception:
        try:
            return genai.GenerativeModel(FALLBACK_MODEL)
        except Exception:
            return None

def usd_to_inr(amount_usd: float, exchange_rate: float = 83.0) -> float:
    """Convert USD amount to INR using the specified exchange rate."""
    return round(amount_usd * exchange_rate, 2)

def extract_json_from_response(text: str) -> dict:
    """Extract and parse JSON from a Gemini response string."""
    text = text.strip()
    
    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass
    
    # Try finding markdown code fences ```json ... ``` or ``` ... ```
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if json_match:
        try:
            return json.loads(json_match.group(1).strip())
        except Exception:
            pass

    # Try finding first { and last }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except Exception:
            pass

    raise ValueError("Could not extract valid JSON from model response")

# ----------------- Input Models -----------------

class HomeBudgetInput(BaseModel):
    total_budget: float
    num_lights: int = 0
    num_fans: int = 0
    num_furniture: int = 0
    num_dining_tables: int = 0
    has_living_room: bool = False
    has_kitchen: bool = False
    has_bedroom: bool = False
    additional_requirements: Optional[str] = ""

class PartyBudgetInput(BaseModel):
    total_budget: float
    num_guests: int = 1
    party_type: str = "Birthday"
    venue_type: Optional[str] = "Home"
    needs_catering: bool = False
    needs_decoration: bool = False
    needs_entertainment: bool = False
    additional_requirements: Optional[str] = ""

class JewelryBudgetInput(BaseModel):
    total_budget: float
    occasion: str = "Birthday"
    preferences: Optional[str] = ""

# ----------------- Fallback Generators -----------------

def generate_fallback_home_recommendations(budget_input: HomeBudgetInput) -> dict:
    """Generate intelligent, realistic home recommendations when AI is offline."""
    total = budget_input.total_budget
    categories = []
    
    # Calculate allocation targets
    lights_qty = max(1, budget_input.num_lights) if budget_input.num_lights > 0 else (4 if budget_input.has_living_room else 2)
    fans_qty = max(1, budget_input.num_fans) if budget_input.num_fans > 0 else (2 if budget_input.has_bedroom else 1)
    furniture_qty = max(1, budget_input.num_furniture) if budget_input.num_furniture > 0 else 2
    dining_qty = max(1, budget_input.num_dining_tables) if budget_input.num_dining_tables > 0 else 1

    light_unit_price = round(min(total * 0.15 / max(1, lights_qty), 500.0), 2)
    fan_unit_price = round(min(total * 0.25 / max(1, fans_qty), 2200.0), 2)
    furniture_unit_price = round(min(total * 0.35 / max(1, furniture_qty), 4500.0), 2)
    dining_unit_price = round(min(total * 0.20 / max(1, dining_qty), 7000.0), 2)

    categories.append({
        "category": "Lighting",
        "allocation": round(light_unit_price * lights_qty, 2),
        "items": [
            {
                "name": "Philips / Wipro Warm White LED Smart Bulb & Downlights",
                "description": "Energy-efficient 9W/12W warm white LED bulbs with anti-glare diffuser for ambient room illumination.",
                "estimated_price": light_unit_price,
                "quantity": lights_qty,
                "search_terms": "LED warm white downlight bulbs Philips"
            }
        ]
    })

    categories.append({
        "category": "Ceiling Fans",
        "allocation": round(fan_unit_price * fans_qty, 2),
        "items": [
            {
                "name": "Havells / Crompton High-Speed Ceiling Fan (1200mm)",
                "description": "BEE 5-star energy saving ceiling fan with silent copper motor and aerodynamically balanced blades.",
                "estimated_price": fan_unit_price,
                "quantity": fans_qty,
                "search_terms": "Havells Crompton 1200mm high speed ceiling fan"
            }
        ]
    })

    furniture_items = []
    if furniture_qty > 0:
        furniture_items.append({
            "name": "Nilkamal / Wakefit Modern Living Accent Chair & Side Stool",
            "description": "Ergonomic, modern upholstered accent seating with sturdy solid wood legs for comfort and durability.",
            "estimated_price": furniture_unit_price,
            "quantity": furniture_qty,
            "search_terms": "Nilkamal modern accent chair living room"
        })
    if budget_input.num_dining_tables > 0:
        furniture_items.append({
            "name": "IKEA / Amazon Brand Compact Solid Wood Dining Table",
            "description": "Minimalist 4-seater wooden dining table with water-resistant smooth oak finish suitable for modern spaces.",
            "estimated_price": dining_unit_price,
            "quantity": dining_qty,
            "search_terms": "solid wood 4 seater dining table compact"
        })
    
    furniture_total = sum(i["estimated_price"] * i["quantity"] for i in furniture_items)
    categories.append({
        "category": "Furniture",
        "allocation": round(furniture_total, 2),
        "items": furniture_items
    })

    total_spent = sum(c["allocation"] for c in categories)
    if total_spent > total:
        scale = (total * 0.92) / total_spent
        for c in categories:
            for item in c["items"]:
                item["estimated_price"] = round(item["estimated_price"] * scale, 2)
            c["allocation"] = round(sum(i["estimated_price"] * i["quantity"] for i in c["items"]), 2)
        total_spent = sum(c["allocation"] for c in categories)

    remaining = round(max(0.0, total - total_spent), 2)

    calc_table = []
    for c in categories:
        count = sum(i["quantity"] for i in c["items"])
        pct = round((c["allocation"] / total) * 100, 1) if total > 0 else 0
        calc_table.append({
            "category": c["category"],
            "items_count": count,
            "total_cost": c["allocation"],
            "percentage_of_budget": pct
        })

    return {
        "total_budget": total,
        "budget_breakdown": categories,
        "calculation_table": calc_table,
        "remaining_budget": remaining,
        "additional_suggestions": [
            "Consider purchasing combo packages or festive bundles on Amazon and IKEA for additional 10-15% discount.",
            "Check local manufacturer outlets or factory-direct stores for solid wood furniture at competitive rates.",
            "Opt for 5-star BEE energy-certified appliances to drastically reduce monthly electricity expenditures."
        ]
    }

def generate_fallback_party_recommendations(budget_input: PartyBudgetInput) -> dict:
    """Generate intelligent party recommendations when AI is offline."""
    total = budget_input.total_budget
    guests = max(1, budget_input.num_guests)
    party_type = budget_input.party_type or "Celebration"
    venue_type = budget_input.venue_type or "Home / Private Space"

    # Proportional allocations
    catering_alloc = round(total * 0.45, 2) if budget_input.needs_catering else round(total * 0.25, 2)
    decor_alloc = round(total * 0.25, 2) if budget_input.needs_decoration else round(total * 0.15, 2)
    entertain_alloc = round(total * 0.20, 2) if budget_input.needs_entertainment else round(total * 0.10, 2)
    contingency_alloc = round(total * 0.10, 2)

    categories = [
        {
            "category": "catering",
            "allocation": catering_alloc,
            "items": [
                {
                    "name": f"Curated Party Platter & Buffet for {guests} Guests",
                    "description": f"Gourmet multi-course party catering package including appetizers, mocktails, main course, and dessert.",
                    "estimated_price": catering_alloc,
                    "quantity": 1,
                    "search_terms": f"party catering food box {party_type.lower()}"
                }
            ]
        },
        {
            "category": "decoration",
            "allocation": decor_alloc,
            "items": [
                {
                    "name": f"Festive Theme Decor & Balloon Arch Set",
                    "description": f"Complete DIY decoration kit with LED fairy lights, backdrop foil curtains, banners, and balloon garland.",
                    "estimated_price": decor_alloc,
                    "quantity": 1,
                    "search_terms": f"{party_type.lower()} theme party decoration kit balloons"
                }
            ]
        },
        {
            "category": "entertainment",
            "allocation": entertain_alloc,
            "items": [
                {
                    "name": "Bluetooth Party Speaker & Game Activity Kit",
                    "description": "High-bass party speaker rental/purchase with fun group party board games and digital music playlist subscription.",
                    "estimated_price": round(entertain_alloc * 0.6, 2),
                    "quantity": 1,
                    "search_terms": "party games group activity kit bluetooth speaker"
                },
                {
                    "name": f"Return Favors & Souvenirs for {guests} Guests",
                    "description": "Custom packaged return gift tokens and sweet celebration hampers for all attendees.",
                    "estimated_price": round(entertain_alloc * 0.4, 2),
                    "quantity": guests,
                    "search_terms": f"party return gifts favors pack of {guests}"
                }
            ]
        },
        {
            "category": "contingency",
            "allocation": contingency_alloc,
            "items": [
                {
                    "name": "Emergency & Miscellaneous Supplies Reserve",
                    "description": "Buffer fund for extra ice, beverages, takeaway disposables, and last-minute delivery charges.",
                    "estimated_price": contingency_alloc,
                    "quantity": 1,
                    "search_terms": "party disposables napkins cutlery cups"
                }
            ]
        }
    ]

    venue_sugg = [
        {
            "name": f"Selected {venue_type} Event Space",
            "type": venue_type,
            "capacity": max(guests, 20),
            "estimated_cost": 0.0 if "home" in venue_type.lower() else round(total * 0.3, 2),
            "search_terms": f"{venue_type} venue rental near me for {guests} people"
        }
    ]

    calc_table = []
    for c in categories:
        cnt = sum(i.get("quantity", 1) for i in c["items"])
        pct = round((c["allocation"] / total) * 100, 1) if total > 0 else 0
        calc_table.append({
            "category": c["category"].title(),
            "items_count": cnt,
            "total_cost": c["allocation"],
            "percentage_of_budget": pct
        })

    total_spent = sum(c["allocation"] for c in categories)
    remaining = round(max(0.0, total - total_spent), 2)

    return {
        "total_budget": total,
        "budget_breakdown": categories,
        "venue_suggestions": venue_sugg,
        "calculation_table": calc_table,
        "remaining_budget": remaining,
        "additional_suggestions": [
            "Order finger foods and appetizers in advance via Swiggy or Zomato party orders for bulk discounts.",
            "Use Spotify or Apple Music party playlists to save significantly on DJ or live music expenses.",
            "Incorporate DIY photo booths with fairy lights and prop cutouts for instagram-worthy memories within budget."
        ]
    }

def generate_fallback_jewelry_recommendations(budget_input: JewelryBudgetInput, image_path: Optional[str] = None) -> dict:
    """Generate intelligent jewelry recommendations with optional outfit color matching."""
    total = budget_input.total_budget
    occasion = budget_input.occasion or "Special Event"
    prefs = budget_input.preferences or "Elegant and versatile"

    detected_colors = ["Golden Hue", "Classic Blue", "Subtle White"]
    detected_style = "Contemporary Ethnic"
    detected_formality = "Semi-Formal to Festive"

    if image_path and os.path.exists(image_path):
        try:
            with Image.open(image_path) as im:
                im = im.convert("RGB").resize((50, 50))
                colors = im.getcolors(2500)
                if colors:
                    colors.sort(reverse=True, key=lambda x: x[0])
                    # Pick top 2 dominant colors
                    top_rgb = [c[1] for c in colors[:2]]
                    color_names = []
                    for r, g, b in top_rgb:
                        if r > 180 and g > 180 and b > 180:
                            color_names.append("Ivory / White")
                        elif r < 60 and g < 60 and b < 60:
                            color_names.append("Charcoal Black")
                        elif r > 150 and g < 90 and b < 90:
                            color_names.append("Crimson Red")
                        elif b > 140 and r < 100:
                            color_names.append("Royal Navy Blue")
                        elif g > 130 and r < 100:
                            color_names.append("Emerald Green")
                        elif r > 180 and g > 140 and b < 80:
                            color_names.append("Warm Gold / Ochre")
                        else:
                            color_names.append(f"RGB({r},{g},{b}) Tone")
                    detected_colors = color_names
        except Exception:
            pass

    # Budget breakdown into 3-4 coordinated jewelry pieces
    p1 = round(total * 0.32, 2)
    p2 = round(total * 0.28, 2)
    p3 = round(total * 0.25, 2)
    spent = p1 + p2 + p3
    remaining = round(max(0.0, total - spent), 2)

    recommendations = [
        {
            "item_type": "Necklace / Pendant",
            "name": f"Delicate 18K Gold Plated Solitaire Pendant & Chain",
            "description": f"Exquisite zircon-studded pendant necklace, styled to complement your outfit neckline for {occasion}.",
            "style": f"{detected_style} / Minimalist",
            "estimated_price": p1,
            "search_terms": f"gold plated solitaire pendant necklace for {occasion}"
        },
        {
            "item_type": "Earrings / Studs",
            "name": "Classic Pear-Cut Crystal Drop Earrings",
            "description": f"Lightweight hypoallergenic dangling earrings that catch the light elegantly without overpowering the face.",
            "style": "Graceful Statement",
            "estimated_price": p2,
            "search_terms": f"crystal drop earrings pear cut {occasion}"
        },
        {
            "item_type": "Bracelet / Bangle",
            "name": "Sleek Adjustable Tennis Cuff Bracelet",
            "description": "Modern silver-toned cuff with micro-pave cubic zirconia stones, perfect for day-to-night transitions.",
            "style": "Contemporary Chic",
            "estimated_price": p3,
            "search_terms": f"adjustable tennis bracelet cubic zirconia"
        }
    ]

    return {
        "total_budget": total,
        "outfit_analysis": {
            "colors": detected_colors,
            "style": detected_style,
            "formality": detected_formality
        },
        "jewelry_recommendations": recommendations,
        "remaining_budget": remaining,
        "styling_tips": [
            f"Balance your jewelry focal point: when wearing prominent earrings, keep neckpieces subtle and understated.",
            f"Match the metallic undertones with your outfit details (gold tones for warm palettes, silver/platinum for cooler shades).",
            "Choose lightweight, anti-tarnish jewelry with skin-friendly rhodium or gold plating for comfortable prolonged wear."
        ]
    }

# ----------------- Main Functions -----------------

def get_home_recommendations(budget_input: HomeBudgetInput) -> dict:
    """Generate home interior recommendations within budget for Indian market."""
    model = get_gemini_model()
    result = None

    if model and GEMINI_API_KEY:
        try:
            prompt = f"""
            I need interior design product recommendations for a home in India with a total budget of ₹{budget_input.total_budget:.2f}.
            Requirements:
            - {budget_input.num_lights} lights/lighting fixtures
            - {budget_input.num_fans} ceiling fans
            - {budget_input.num_furniture} furniture pieces
            - {budget_input.num_dining_tables} dining tables

            Additional rooms to consider:
            {"- Living room" if budget_input.has_living_room else ""}
            {"- Kitchen" if budget_input.has_kitchen else ""}
            {"- Bedroom" if budget_input.has_bedroom else ""}

            Additional requirements: {budget_input.additional_requirements or "None"}

            Please provide a detailed budget breakdown with product recommendations **available in India**.
            Use **Indian brands and pricing**. Include **search terms** suitable for Indian shopping platforms.

            Format your response as valid JSON with the following structure:
            {{
              "total_budget": {budget_input.total_budget:.2f},
              "budget_breakdown": [
                {{
                  "category": "Lighting",
                  "allocation": 0.0,
                  "items": [
                    {{
                      "name": "Item Name",
                      "description": "Detailed description",
                      "estimated_price": 0.0,
                      "quantity": 1,
                      "search_terms": "search query"
                    }}
                  ]
                }}
              ],
              "calculation_table": [
                {{
                  "category": "Lighting",
                  "items_count": 0,
                  "total_cost": 0.0,
                  "percentage_of_budget": 0.0
                }}
              ],
              "remaining_budget": 0.0,
              "additional_suggestions": ["Suggestion 1", "Suggestion 2"]
            }}
            Ensure total costs stay within budget. Include search terms for each item to find on shopping websites like Flipkart, Amazon India, IKEA. Return ONLY pure JSON.
            """
            response = model.generate_content(prompt)
            result = extract_json_from_response(response.text)
        except Exception as e:
            print(f"Gemini home planning call failed: {e}. Using intelligent fallback.")
            result = None

    if not result:
        result = generate_fallback_home_recommendations(budget_input)

    # Add shopping links for each item
    for category in result.get("budget_breakdown", []):
        for item in category.get("items", []):
            search_terms = item.get("search_terms", "") or item.get("name", "")
            if search_terms:
                encoded = urllib.parse.quote_plus(search_terms)
                item["shopping_links"] = {
                    "amazon": f"https://www.amazon.in/s?k={encoded}",
                    "flipkart": f"https://www.flipkart.com/search?q={encoded}",
                    "ikea": f"https://www.ikea.com/in/en/search/?q={encoded}",
                    "myntra": f"https://www.myntra.com/search?q={encoded}",
                    "ajio": f"https://www.ajio.com/search/?text={encoded}"
                }

    return result

def get_party_recommendations(budget_input: PartyBudgetInput) -> dict:
    """Generate party planning recommendations within budget for Indian market."""
    model = get_gemini_model()
    result = None

    if model and GEMINI_API_KEY:
        try:
            prompt = f"""
            I need party planning recommendations for India with a total budget of ₹{budget_input.total_budget:.2f}.
            Party details:
            - Type: {budget_input.party_type}
            - Number of guests: {budget_input.num_guests}
            - Venue type: {budget_input.venue_type or "Not specified"}
            - Catering needed: {"Yes" if budget_input.needs_catering else "No"}
            - Decoration needed: {"Yes" if budget_input.needs_decoration else "No"}
            - Entertainment needed: {"Yes" if budget_input.needs_entertainment else "No"}

            Additional requirements: {budget_input.additional_requirements or "None"}

            Please provide a detailed budget breakdown with specific recommendations available in India using INR prices.
            Use Indian brands, services, and typical cost expectations.

            Format your response as valid JSON with the following structure:
            {{
              "total_budget": {budget_input.total_budget:.2f},
              "budget_breakdown": [
                {{
                  "category": "catering",
                  "allocation": 0.0,
                  "items": [
                    {{
                      "name": "Service / Item name",
                      "description": "Details",
                      "estimated_price": 0.0,
                      "quantity": 1,
                      "search_terms": "search query"
                    }}
                  ]
                }}
              ],
              "venue_suggestions": [
                {{
                  "name": "Venue Name",
                  "type": "Venue Type",
                  "capacity": 50,
                  "estimated_cost": 0.0,
                  "search_terms": "venue search terms"
                }}
              ],
              "remaining_budget": 0.0,
              "additional_suggestions": ["Suggestion 1", "Suggestion 2"]
            }}
            Ensure all costs are in INR and total does not exceed the given budget.
            Provide search terms suitable for Indian websites such as BookMyShow, Swiggy, Flipkart, etc. Return ONLY pure JSON.
            """
            response = model.generate_content(prompt)
            result = extract_json_from_response(response.text)
        except Exception as e:
            print(f"Gemini party planning call failed: {e}. Using intelligent fallback.")
            result = None

    if not result:
        result = generate_fallback_party_recommendations(budget_input)

    # Create INR calculation table if not already populated
    if not result.get("calculation_table"):
        calc_table = []
        for cat in result.get("budget_breakdown", []):
            cat_name = cat.get("category", "Misc").title()
            items_count = sum(item.get("quantity", 1) for item in cat.get("items", []))
            total_cost = cat.get("allocation", 0.0)
            total_b = result.get("total_budget", budget_input.total_budget)
            pct = round((total_cost / total_b * 100), 1) if total_b > 0 else 0
            calc_table.append({
                "category": cat_name,
                "items_count": items_count,
                "total_cost": total_cost,
                "percentage_of_budget": pct
            })
        result["calculation_table"] = calc_table

    # Map relevant shopping platforms per category as specified in PDF page 15
    category_platforms = {
        "venue": ["google", "booking", "makemytrip", "oyorooms", "nobroker"],
        "catering": ["swiggy", "zomato", "bigbasket"],
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
        "contingency": ["amazon", "flipkart", "google"]
    }
    default_platforms = ["amazon", "flipkart", "google"]

    for category in result.get("budget_breakdown", []):
        cat_name = category.get("category", "").lower()
        rel_platforms = category_platforms.get(cat_name, default_platforms)
        for item in category.get("items", []):
            st = item.get("search_terms", "") or item.get("name", "")
            if st:
                q = urllib.parse.quote_plus(st)
                links = {}
                if "amazon" in rel_platforms:
                    links["amazon"] = f"https://www.amazon.in/s?k={q}"
                if "flipkart" in rel_platforms:
                    links["flipkart"] = f"https://www.flipkart.com/search?q={q}"
                if "swiggy" in rel_platforms:
                    links["swiggy"] = f"https://www.swiggy.com/search?query={q}"
                if "zomato" in rel_platforms:
                    links["zomato"] = f"https://www.zomato.com/search?q={q}"
                if "bigbasket" in rel_platforms:
                    links["bigbasket"] = f"https://www.bigbasket.com/ps/?q={q}"
                if "bookmyshow" in rel_platforms:
                    links["bookmyshow"] = f"https://in.bookmyshow.com/search?q={q}"
                if "myntra" in rel_platforms:
                    links["myntra"] = f"https://www.myntra.com/search?q={q}"
                if "meesho" in rel_platforms:
                    links["meesho"] = f"https://www.meesho.com/search?q={q}"
                if "google" in rel_platforms:
                    links["google"] = f"https://www.google.com/search?q={q}"
                if "booking" in rel_platforms:
                    links["booking"] = f"https://www.booking.com/search.html?ss={q}"
                if "makemytrip" in rel_platforms:
                    links["makemytrip"] = f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={q}"
                if "oyorooms" in rel_platforms:
                    links["oyorooms"] = f"https://www.oyorooms.com/search/?location={q}"
                if "nobroker" in rel_platforms:
                    links["nobroker"] = f"https://www.nobroker.in/property/search/?searchTerm={q}"
                item["shopping_links"] = links

    # Add search links for venue suggestions
    for venue in result.get("venue_suggestions", []):
        v_st = venue.get("search_terms", "") or venue.get("name", "")
        if v_st:
            vq = urllib.parse.quote_plus(v_st)
            venue["search_links"] = {
                "google": f"https://www.google.com/search?q={vq}",
                "booking": f"https://www.booking.com/search.html?ss={vq}",
                "makemytrip": f"https://www.makemytrip.com/hotels/hotel-listing/?searchText={vq}",
                "oyorooms": f"https://www.oyorooms.com/search/?location={vq}",
                "nobroker": f"https://www.nobroker.in/property/search/?searchTerm={vq}"
            }

    return result

def get_jewelry_recommendations(budget_input: JewelryBudgetInput, image_path: Optional[str] = None) -> dict:
    """Generate jewelry recommendations based on optional uploaded dress image and budget in INR."""
    model = get_gemini_model()
    result = None

    base_prompt = f"""
    I need jewelry recommendations for India with a total budget of ₹{budget_input.total_budget:.2f}.
    Occasion: {budget_input.occasion}
    Preferences: {budget_input.preferences or "Not specified"}
    Provide only India-relevant styles, availability, and price ranges in INR.
    """

    if model and GEMINI_API_KEY:
        try:
            if image_path and os.path.exists(image_path):
                img = Image.open(image_path)
                prompt = base_prompt + """
                An image of the outfit is uploaded. Suggest jewelry that complements it, considering color, design, and occasion appropriateness.
                Format the output as valid JSON:
                {
                  "outfit_analysis": {
                    "colors": ["Detected Color 1", "Detected Color 2"],
                    "style": "Ethnic / Western / Fusion",
                    "formality": "Festive / Formal / Casual"
                  },
                  "total_budget": 0.0,
                  "jewelry_recommendations": [
                    {
                      "item_type": "Bracelet / Ring / Watch / Necklace",
                      "name": "Product Name",
                      "description": "Design and material description",
                      "style": "Style type",
                      "estimated_price": 0.0,
                      "search_terms": "shopping query"
                    }
                  ],
                  "remaining_budget": 0.0,
                  "styling_tips": ["Tip 1", "Tip 2"]
                }
                Make sure prices are in INR and stay within budget. Include Indian-friendly search terms for shopping. Return ONLY JSON.
                """
                response = model.generate_content([prompt, img])
            else:
                prompt = base_prompt + """
                Format the output as valid JSON:
                {
                  "outfit_analysis": {
                    "colors": ["Coordinated palette"],
                    "style": "Contemporary Elegant",
                    "formality": "Celebration"
                  },
                  "total_budget": 0.0,
                  "jewelry_recommendations": [
                    {
                      "item_type": "Bracelet / Ring / Watch / Necklace",
                      "name": "Product Name",
                      "description": "Design and material description",
                      "style": "Style type",
                      "estimated_price": 0.0,
                      "search_terms": "shopping query"
                    }
                  ],
                  "remaining_budget": 0.0,
                  "styling_tips": ["Tip 1", "Tip 2"]
                }
                Keep prices in INR and relevant to Indian brands. Return ONLY JSON.
                """
                response = model.generate_content(prompt)
            result = extract_json_from_response(response.text)
        except Exception as e:
            print(f"Gemini jewelry planning call failed: {e}. Using intelligent fallback.")
            result = None

    if not result:
        result = generate_fallback_jewelry_recommendations(budget_input, image_path)

    # Ensure total_budget is populated
    if not result.get("total_budget"):
        result["total_budget"] = budget_input.total_budget

    # Add shopping links for each jewelry item
    for item in result.get("jewelry_recommendations", []):
        st = item.get("search_terms", "") or item.get("name", "")
        if st:
            q = urllib.parse.quote_plus(st)
            item["shopping_links"] = {
                "amazon": f"https://www.amazon.in/s?k={q}",
                "flipkart": f"https://www.flipkart.com/search?q={q}",
                "bluestone": f"https://www.bluestone.com/search.html?query={q}",
                "tanishq": f"https://www.tanishq.co.in/search?q={q}",
                "caratlane": f"https://www.caratlane.com/search?q={q}",
                "melorra": f"https://www.melorra.com/search?q={q}",
                "meesho": f"https://www.meesho.com/search?q={q}"
            }

    return result
