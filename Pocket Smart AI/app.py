import os
import json
import re
import base64
import shutil
import urllib.parse
from fastapi import FastAPI, HTTPException, Depends, File, UploadFile, Form, Request, status, Cookie
from fastapi.responses import JSONResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from PIL import Image
from io import BytesIO
import google.generativeai as genai
from dotenv import load_dotenv
import asyncio
import uuid

# Import recommendation helpers
import gemini_utils
from gemini_utils import (
    HomeBudgetInput, PartyBudgetInput, JewelryBudgetInput,
    get_home_recommendations, get_party_recommendations, get_jewelry_recommendations,
    usd_to_inr
)

# Load environment variables
load_dotenv()

# FastAPI app initialization
app = FastAPI(title="PocketSmart: AI Budget Planner")

SECRET_KEY = os.getenv("SECRET_KEY", "pocketsmart_ai_super_secret_jwt_key_2026_production")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
os.makedirs("static/uploads", exist_ok=True)
os.makedirs("data", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

def render_template(request: Request, name: str, context: Optional[dict] = None, status_code: int = 200) -> HTMLResponse:
    ctx = {"request": request}
    if context:
        ctx.update(context)
    return templates.TemplateResponse(request=request, name=name, context=ctx, status_code=status_code)

# ----------------- User and Session Models -----------------

class RegisterUser(BaseModel):
    username: str
    email: EmailStr
    full_name: Optional[str] = None
    password: str

class UserInDB(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    hashed_password: str
    disabled: bool = False

class Token(BaseModel):
    access_token: str
    token_type: str

class UserSession(BaseModel):
    username: str
    login_time: datetime
    last_activity: datetime
    user_data: Dict[str, Any] = {}

class RecommendationRecord(BaseModel):
    id: str
    timestamp: str
    recommendation_type: str
    input_summary: str
    result_summary: str
    full_input: Dict[str, Any]
    full_result: Dict[str, Any]

# ----------------- In-Memory & File-Backed Storage -----------------

USERS_FILE = os.path.join("data", "users.json")
HISTORY_FILE = os.path.join("data", "history.json")

def load_json_file(path: str, default: Any):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default

def save_json_file(path: str, data: Any):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        print(f"Error saving to {path}: {e}")

# Pre-seed users database with default demo user "sai"
users_db: Dict[str, dict] = load_json_file(USERS_FILE, {})
if "sai" not in users_db:
    users_db["sai"] = {
        "username": "sai",
        "email": "sai@pocketsmart.ai",
        "full_name": "Sai Kumar",
        "hashed_password": pwd_context.hash("password123"),
        "disabled": False
    }
    save_json_file(USERS_FILE, users_db)

# Active sessions and recommendation history
active_sessions: Dict[str, Dict[str, Any]] = {}
blacklisted_tokens = set()

# Pre-seed history with realistic sample data for demo user "sai"
user_recommendations: Dict[str, List[Dict[str, Any]]] = load_json_file(HISTORY_FILE, {})
if "sai" not in user_recommendations or len(user_recommendations["sai"]) == 0:
    user_recommendations["sai"] = [
        {
            "id": "rec-demo-home-1",
            "timestamp": "May 22, 2026, 12:02 PM",
            "recommendation_type": "home",
            "input_summary": "Rooms: Living Room, Kitchen | Lights: 5, Fans: 4, Furniture: 2",
            "result_summary": "Budget: ₹5,000 | Remaining: ₹500",
            "full_input": {"total_budget": 5000, "num_lights": 5, "num_fans": 4, "num_furniture": 2, "has_living_room": True, "has_kitchen": True},
            "full_result": get_home_recommendations(HomeBudgetInput(total_budget=5000, num_lights=5, num_fans=4, num_furniture=2, has_living_room=True, has_kitchen=True))
        },
        {
            "id": "rec-demo-party-2",
            "timestamp": "May 22, 2026, 12:05 PM",
            "recommendation_type": "party",
            "input_summary": "Party Type: wedding | Guests: 3 | Needs: Catering, Entertainment",
            "result_summary": "Budget: ₹5,000 | Remaining: ₹0",
            "full_input": {"total_budget": 5000, "num_guests": 3, "party_type": "Wedding", "needs_catering": True, "needs_entertainment": True},
            "full_result": get_party_recommendations(PartyBudgetInput(total_budget=5000, num_guests=3, party_type="Wedding", needs_catering=True, needs_entertainment=True))
        },
        {
            "id": "rec-demo-jewelry-3",
            "timestamp": "May 22, 2026, 12:08 PM",
            "recommendation_type": "jewelry",
            "input_summary": "Occasion: Birthday | With outfit image: Yes",
            "result_summary": "Budget: ₹5,000 | Remaining: ₹800",
            "full_input": {"total_budget": 5000, "occasion": "Birthday", "preferences": "Elegant minimalist"},
            "full_result": get_jewelry_recommendations(JewelryBudgetInput(total_budget=5000, occasion="Birthday", preferences="Elegant minimalist"))
        }
    ]
    save_json_file(HISTORY_FILE, user_recommendations)

# ----------------- Auth Helpers -----------------

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_token_from_request(request: Request) -> Optional[str]:
    # Check Cookie first
    token = request.cookies.get("access_token")
    if token:
        if token.startswith("Bearer "):
            return token.replace("Bearer ", "")
        return token
    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    return None

async def get_current_user(request: Request) -> Optional[UserInDB]:
    token = await get_token_from_request(request)
    if not token or token in blacklisted_tokens:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
        user_dict = users_db.get(username)
        if user_dict is None:
            return None
        return UserInDB(**user_dict)
    except JWTError:
        return None

async def get_current_active_user(request: Request) -> UserInDB:
    user = await get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if user.disabled:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    # Update last activity in active_sessions
    if user.username in active_sessions:
        active_sessions[user.username]["last_activity"] = datetime.utcnow()
    return user

def save_to_history(username: str, recommendation_type: str, input_data: dict, result: dict):
    """Save recommendation query and result to user history."""
    if username not in user_recommendations:
        user_recommendations[username] = []
    
    now = datetime.now()
    timestamp_str = now.strftime("%b %d, %Y, %I:%M %p")
    rec_id = f"rec-{uuid.uuid4().hex[:8]}"

    total_budget = result.get("total_budget", input_data.get("total_budget", 0))
    rem_budget = result.get("remaining_budget", 0)

    if recommendation_type == "home":
        rooms = []
        if input_data.get("has_living_room"): rooms.append("Living Room")
        if input_data.get("has_kitchen"): rooms.append("Kitchen")
        if input_data.get("has_bedroom"): rooms.append("Bedroom")
        rooms_str = ", ".join(rooms) if rooms else "Standard"
        input_summary = f"Rooms: {rooms_str} | Lights: {input_data.get('num_lights', 0)}, Fans: {input_data.get('num_fans', 0)}, Furniture: {input_data.get('num_furniture', 0)}"
        result_summary = f"Budget: ₹{total_budget:,.0f} | Remaining: ₹{rem_budget:,.0f}"

    elif recommendation_type == "party":
        ptype = input_data.get("party_type", "Party")
        guests = input_data.get("num_guests", 1)
        needs = []
        if input_data.get("needs_catering"): needs.append("Catering")
        if input_data.get("needs_decoration"): needs.append("Decoration")
        if input_data.get("needs_entertainment"): needs.append("Entertainment")
        needs_str = ", ".join(needs) if needs else "Standard"
        input_summary = f"Party Type: {ptype} | Guests: {guests} | Needs: {needs_str}"
        result_summary = f"Budget: ₹{total_budget:,.0f} | Remaining: ₹{rem_budget:,.0f}"

    else: # jewelry
        occ = input_data.get("occasion", "General")
        has_img = "Yes" if input_data.get("image") or input_data.get("image_path") else "No"
        input_summary = f"Occasion: {occ} | With outfit image: {has_img}"
        result_summary = f"Budget: ₹{total_budget:,.0f} | Remaining: ₹{rem_budget:,.0f}"

    record = {
        "id": rec_id,
        "timestamp": timestamp_str,
        "recommendation_type": recommendation_type,
        "input_summary": input_summary,
        "result_summary": result_summary,
        "full_input": input_data,
        "full_result": result
    }
    user_recommendations[username].insert(0, record)
    save_json_file(HISTORY_FILE, user_recommendations)
    return record

# ----------------- Authentication Routes -----------------

@app.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Serve PocketSmart AI landing page"""
    user = await get_current_user(request)
    return render_template(request, "index.html", {"user": user})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page"""
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return render_template(request, "login.html")

@app.post("/token")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint to get JWT access token"""
    user_dict = users_db.get(form_data.username)
    if not user_dict or not verify_password(form_data.password, user_dict["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_dict["username"]}, expires_delta=access_token_expires
    )

    # Initialize user session
    active_sessions[user_dict["username"]] = {
        "username": user_dict["username"],
        "login_time": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "user_data": {}
    }

    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return response

@app.post("/login")
async def process_form_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Form login endpoint that redirects back to dashboard with cookie set"""
    user_dict = users_db.get(username)
    if not user_dict or not verify_password(password, user_dict["hashed_password"]):
        return render_template(
            request,
            "login.html",
            {"error": "Invalid username or password. Please try again."}
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_dict["username"]}, expires_delta=access_token_expires
    )

    active_sessions[user_dict["username"]] = {
        "username": user_dict["username"],
        "login_time": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "user_data": {}
    }

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return response

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration page"""
    user = await get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return render_template(request, "register.html")

@app.post("/register")
async def process_register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...)
):
    """Handle new user registration"""
    if password != confirm_password:
        return render_template(
            request,
            "register.html",
            {"error": "Passwords do not match. Please verify."}
        )
    
    if username in users_db:
        return render_template(
            request,
            "register.html",
            {"error": "Username already taken. Please choose another."}
        )
    
    users_db[username] = {
        "username": username,
        "email": email,
        "full_name": username.title(),
        "hashed_password": get_password_hash(password),
        "disabled": False
    }
    save_json_file(USERS_FILE, users_db)

    # Automatically log the newly registered user in
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": username}, expires_delta=access_token_expires
    )

    active_sessions[username] = {
        "username": username,
        "login_time": datetime.utcnow(),
        "last_activity": datetime.utcnow(),
        "user_data": {}
    }

    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax"
    )
    return response

@app.get("/logout")
@app.post("/logout")
async def logout(request: Request):
    """Logout user by blacklisting their token and clearing session"""
    token = await get_token_from_request(request)
    if token:
        blacklisted_tokens.add(token)
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            username = payload.get("sub")
            if username and username in active_sessions:
                del active_sessions[username]
        except JWTError:
            pass

    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="access_token")
    return response

# ----------------- Dashboard & Session Routes -----------------

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """User dashboard page displaying recent recommendations and shortcuts"""
    user_history = user_recommendations.get(current_user.username, [])[:5]
    return render_template(
        request,
        "dashboard.html",
        {"user": current_user, "recent_history": user_history}
    )

@app.get("/session-info")
async def get_session_info(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Get current user's session information"""
    if current_user.username in active_sessions:
        session = active_sessions[current_user.username]
        login_t = session.get("login_time", datetime.utcnow())
        last_t = session.get("last_activity", datetime.utcnow())
        return {
            "username": session.get("username", current_user.username),
            "login_time": login_t.isoformat() if isinstance(login_t, datetime) else str(login_t),
            "last_activity": last_t.isoformat() if isinstance(last_t, datetime) else str(last_t),
            "session_duration_minutes": (datetime.utcnow() - login_t).total_seconds() // 60 if isinstance(login_t, datetime) else 0,
            "user_data": session.get("user_data", {})
        }
    else:
        raise HTTPException(status_code=404, detail="No active session found")

@app.post("/session-data")
async def update_session_data(data: Dict[str, Any], request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Update current user's session data"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username]["user_data"].update(data)
        active_sessions[current_user.username]["last_activity"] = datetime.utcnow()
        return {"message": "Session data updated", "data": active_sessions[current_user.username]["user_data"]}
    else:
        raise HTTPException(status_code=404, detail="No active session found")

# ----------------- Planner 1: Home Interior Planner -----------------

@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Home budget planner page"""
    return render_template(request, "home_planner.html", {"user": current_user})

@app.post("/home-budget")
@app.post("/generate-home")
async def plan_home_budget(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate home budget recommendations"""
    # Support both JSON payload and Form submission
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        budget_input = HomeBudgetInput(**body)
    else:
        form = await request.form()
        budget_input = HomeBudgetInput(
            total_budget=float(form.get("total_budget", 0)),
            num_lights=int(form.get("num_lights", 0)),
            num_fans=int(form.get("num_fans", 0)),
            num_furniture=int(form.get("num_furniture", 0)),
            num_dining_tables=int(form.get("num_dining_tables", 0)),
            has_living_room=bool(form.get("has_living_room") in ["true", "True", "on", "1"]),
            has_kitchen=bool(form.get("has_kitchen") in ["true", "True", "on", "1"]),
            has_bedroom=bool(form.get("has_bedroom") in ["true", "True", "on", "1"]),
            additional_requirements=form.get("additional_requirements", "")
        )

    # Store last budget planning in session data
    if current_user.username in active_sessions:
        active_sessions[current_user.username]["user_data"]["last_home_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "requirements": {
                "lights": budget_input.num_lights,
                "fans": budget_input.num_fans,
                "furniture": budget_input.num_furniture,
                "dining_tables": budget_input.num_dining_tables
            }
        }

    # Get recommendations
    result = get_home_recommendations(budget_input)

    # Save to history
    save_to_history(
        username=current_user.username,
        recommendation_type="home",
        input_data=budget_input.model_dump(),
        result=result
    )

    return result

# ----------------- Planner 2: Party Budget Planner -----------------

@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Party budget planner page"""
    return render_template(request, "party_planner.html", {"user": current_user})

@app.post("/party-budget")
@app.post("/generate-party")
async def plan_party_budget(
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate party budget recommendations"""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        budget_input = PartyBudgetInput(**body)
    else:
        form = await request.form()
        budget_input = PartyBudgetInput(
            total_budget=float(form.get("total_budget", 0)),
            num_guests=int(form.get("num_guests", 1)),
            party_type=form.get("party_type", "Birthday"),
            venue_type=form.get("venue_type", "Home"),
            needs_catering=bool(form.get("needs_catering") in ["true", "True", "on", "1"]),
            needs_decoration=bool(form.get("needs_decoration") in ["true", "True", "on", "1"]),
            needs_entertainment=bool(form.get("needs_entertainment") in ["true", "True", "on", "1"]),
            additional_requirements=form.get("additional_requirements", "")
        )

    # Store last budget planning in session data
    if current_user.username in active_sessions:
        active_sessions[current_user.username]["user_data"]["last_party_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "party_type": budget_input.party_type,
            "guests": budget_input.num_guests
        }

    # Get recommendations
    result = get_party_recommendations(budget_input)

    # Save to history
    save_to_history(
        username=current_user.username,
        recommendation_type="party",
        input_data=budget_input.model_dump(),
        result=result
    )

    return result

# ----------------- Planner 3: Jewelry Budget Planner -----------------

@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Jewelry budget planner page"""
    return render_template(request, "jewelry_planner.html", {"user": current_user})

@app.post("/jewelry-budget")
@app.post("/generate-jewelry")
async def plan_jewelry_budget(
    request: Request,
    total_budget: float = Form(...),
    occasion: str = Form("Birthday"),
    preferences: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Generate jewelry budget recommendations with optional outfit image"""
    budget_input = JewelryBudgetInput(
        total_budget=total_budget,
        occasion=occasion,
        preferences=preferences or ""
    )

    image_path = None
    image_rel_path = None
    if image and image.filename:
        filename = f"{uuid.uuid4().hex}_{image.filename}"
        image_path = os.path.join("static", "uploads", filename)
        with open(image_path, "wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        image_rel_path = f"/static/uploads/{filename}"

    # Store last budget planning in session data
    if current_user.username in active_sessions:
        active_sessions[current_user.username]["user_data"]["last_jewelry_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "occasion": budget_input.occasion,
            "has_image": image_path is not None
        }

    # Get recommendations
    result = get_jewelry_recommendations(budget_input, image_path)
    if image_rel_path:
        result["uploaded_image_url"] = image_rel_path

    # Save to history
    input_history = budget_input.model_dump()
    if image_rel_path:
        input_history["image"] = image_rel_path

    save_to_history(
        username=current_user.username,
        recommendation_type="jewelry",
        input_data=input_history,
        result=result
    )

    return result

# ----------------- History & Details Routes -----------------

@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """History page to view past recommendations"""
    user_items = user_recommendations.get(current_user.username, [])
    return render_template(
        request,
        "history.html",
        {"user": current_user, "history_items": user_items}
    )

@app.get("/recommendation-history")
async def get_recommendation_history(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Get the user's recommendation history JSON"""
    if current_user.username not in user_recommendations:
        return {"history": []}
    
    history_items = user_recommendations[current_user.username]
    summary_list = []
    for item in history_items:
        summary_list.append({
            "id": item["id"],
            "timestamp": item["timestamp"],
            "type": item["recommendation_type"],
            "input": item["input_summary"],
            "summary": item["result_summary"]
        })
    return {"history": summary_list}

@app.get("/recommendations-details/{recommendation_id}")
async def get_recommendation_details(
    recommendation_id: str,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Get full details of a specific recommendation by ID"""
    if current_user.username not in user_recommendations:
        raise HTTPException(status_code=404, detail="No recommendations found")

    for item in user_recommendations[current_user.username]:
        if item["id"] == recommendation_id:
            return {
                "id": item["id"],
                "timestamp": item["timestamp"],
                "type": item["recommendation_type"],
                "input": item["input_summary"],
                "full_input": item.get("full_input", {}),
                "full_result": item["full_result"]
            }

    raise HTTPException(status_code=404, detail="Recommendation not found")

# ----------------- Startup Background Cleanup & Main -----------------

@app.on_event("startup")
async def setup_session_cleanup():
    """Background task to clean up expired sessions every 5 minutes"""
    async def cleanup_expired_sessions():
        while True:
            current_time = datetime.utcnow()
            expired_sessions = [
                username for username, session in list(active_sessions.items())
                if (current_time - session.get("last_activity", current_time)).total_seconds() > 1800
            ]
            for username in expired_sessions:
                if username in active_sessions:
                    print(f"Removing expired session for {username}")
                    del active_sessions[username]
            await asyncio.sleep(300)

    asyncio.create_task(cleanup_expired_sessions())

if __name__ == "__main__":
    import uvicorn
    print("Starting PocketSmart: AI Budget Planner...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
