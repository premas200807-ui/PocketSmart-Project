"""
app.py - PocketSmart AI: Your Smart Budget & Recommendation Assistant
FastAPI backend: routing, JWT auth, session handling, history and planner APIs.

Run:  python app.py      (or)   uvicorn app:app --reload
Open: http://127.0.0.1:8000
"""
import asyncio
import json
import os
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jose import JWTError, jwt
from passlib.context import CryptContext

from gemini_utils import (
    ai_available,
    get_home_recommendations,
    get_jewelry_recommendations,
    get_party_recommendations,
)
from models import (
    HomeBudgetInput,
    JewelryBudgetInput,
    PartyBudgetInput,
    RecommendationHistory,
    RegisterUser,
    Token,
    UserInDB,
    UserSession,
)

# Load environment variables
load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# FastAPI app initialization
app = FastAPI(title="PocketSmart: AI Budget Planner")

SECRET_KEY = os.getenv("SECRET_KEY", "change_this_secret_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)  # Allow optional token

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# ---------------------------------------------------------------------------
# Simple JSON-file storage (users + history survive restarts)
# ---------------------------------------------------------------------------
DATA_DIR = os.path.join(BASE_DIR, "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
os.makedirs(DATA_DIR, exist_ok=True)
_file_lock = threading.Lock()


def _load(path: str) -> Dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(path: str, data: Dict[str, Any]) -> None:
    with _file_lock:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        os.replace(tmp, path)


users_db: Dict[str, Dict[str, Any]] = _load(USERS_FILE)
user_recommendations: Dict[str, List[RecommendationHistory]] = {
    u: [RecommendationHistory(**r) for r in recs] for u, recs in _load(HISTORY_FILE).items()
}
active_sessions: Dict[str, UserSession] = {}
blacklisted_tokens: set = set()


def persist_history() -> None:
    _save(HISTORY_FILE, {u: [r.model_dump() for r in recs] for u, recs in user_recommendations.items()})


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
class NotAuthenticatedException(Exception):
    pass


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    """Browser page requests are redirected to /login; API calls get a 401 JSON."""
    if request.method == "GET" and "text/html" in request.headers.get("accept", ""):
        response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        response.delete_cookie("access_token")
        return response
    return JSONResponse(status_code=401, content={"detail": "Not authenticated. Please log in again."})


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def get_user(db: Dict[str, Dict[str, Any]], username: str) -> Optional[UserInDB]:
    if username in db:
        return UserInDB(**db[username])
    return None


def authenticate_user(db, username: str, password: str) -> Optional[UserInDB]:
    user = get_user(db, username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_token(request: Request) -> Optional[str]:
    """Read the JWT from the cookie, or from an 'Authorization: Bearer' header."""
    token = request.cookies.get("access_token")
    if token:
        return token.replace("Bearer ", "")
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


async def get_current_user(request: Request, token: Optional[str] = None) -> Optional[UserInDB]:
    token = token or await get_token(request)
    if not token or token in blacklisted_tokens:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
    except JWTError:
        return None
    if not username:
        return None
    user = get_user(users_db, username)
    if user:
        # Re-create the session if the server restarted or the session was cleaned up
        now = datetime.utcnow()
        if username not in active_sessions:
            active_sessions[username] = UserSession(
                username=username, login_time=now, last_activity=now, token=token, user_data={}
            )
        else:
            active_sessions[username].last_activity = now
    return user


async def get_current_active_user(request: Request) -> UserInDB:
    user = await get_current_user(request)
    if user is None or user.disabled:
        raise NotAuthenticatedException()
    return user


def save_upload_file(upload: UploadFile) -> str:
    """Save an uploaded outfit image into static/uploads with a timestamped name."""
    ext = os.path.splitext(upload.filename or "")[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="Please upload a JPG, PNG or WEBP image.")
    safe_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}{ext}"
    path = os.path.join(UPLOAD_DIR, safe_name)
    with open(path, "wb") as buffer:
        shutil.copyfileobj(upload.file, buffer)
    if os.path.getsize(path) > 8 * 1024 * 1024:
        os.remove(path)
        raise HTTPException(status_code=400, detail="Image is too large (max 8 MB).")
    return path


def save_to_history(username: str, recommendation_type: str, input_data: Dict[str, Any], result: Dict[str, Any]) -> str:
    """Store a recommendation in the user's history."""
    result_summary = {
        "total_budget": result.get("total_budget"),
        "remaining_budget": result.get("remaining_budget"),
        "categories": [c.get("category") for c in result.get("budget_breakdown", [])],
        "items_count": len(result.get("jewelry_recommendations", []))
        or sum(len(c.get("items", [])) for c in result.get("budget_breakdown", [])),
        "source": result.get("source"),
    }
    entry = RecommendationHistory(
        id=str(uuid.uuid4()),
        username=username,
        timestamp=datetime.now().isoformat(timespec="seconds"),
        recommendation_type=recommendation_type,
        input_summary=input_data,
        result_summary=result_summary,
        full_result=result,
    )
    user_recommendations.setdefault(username, []).append(entry)
    persist_history()
    return entry.id


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Landing page"""
    user = await get_current_user(request)
    return templates.TemplateResponse(request, "index.html", {"user": user})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Serve the login page"""
    try:
        token = await get_token(request)
        if token:
            user = await get_current_user(request, token)
            if user:
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception:
        pass
    return templates.TemplateResponse(request, "login.html", {})


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Serve the registration page"""
    try:
        token = await get_token(request)
        if token:
            user = await get_current_user(request, token)
            if user:
                return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    except Exception:
        pass
    return templates.TemplateResponse(request, "register.html", {})


# ---------------------------------------------------------------------------
# Auth API
# ---------------------------------------------------------------------------
@app.post("/register")
async def register_user(user: RegisterUser):
    """Handle new user registration and securely store credentials"""
    username = user.username.strip().lower()
    if not username.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Username can contain only letters, numbers and _")
    if username in users_db:
        raise HTTPException(status_code=400, detail="Username already registered")
    if "@" not in user.email or "." not in user.email.split("@")[-1]:
        raise HTTPException(status_code=400, detail="Please enter a valid email address")
    if any(u["email"].lower() == user.email.lower() for u in users_db.values()):
        raise HTTPException(status_code=400, detail="Email already registered")

    users_db[username] = {
        "username": username,
        "email": user.email,
        "full_name": user.full_name or username,
        "disabled": False,
        "hashed_password": get_password_hash(user.password),
    }
    _save(USERS_FILE, users_db)
    return {"message": "Registration successful. Please log in.", "username": username}


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login endpoint to get access token"""
    user = authenticate_user(users_db, form_data.username.strip().lower(), form_data.password)
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(data={"sub": user.username}, expires_delta=access_token_expires)

    # Create or update session for the user
    existing_user_data: Dict[str, Any] = {}
    if user.username in active_sessions:
        existing_user_data = active_sessions[user.username].user_data
        old_token = active_sessions[user.username].token
        blacklisted_tokens.add(old_token)

    active_sessions[user.username] = UserSession(
        username=user.username,
        login_time=datetime.utcnow(),
        last_activity=datetime.utcnow(),
        token=access_token,
        user_data=existing_user_data,
    )

    # Return response with cookie
    response = JSONResponse(content={"access_token": access_token, "token_type": "bearer"})
    response.set_cookie(
        key="access_token",
        value=access_token,  # Store token directly without Bearer prefix
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
    )
    return response


@app.post("/logout")
@app.get("/logout")
async def logout(request: Request):
    """Logout user by blacklisting their token and clearing session"""
    token = await get_token(request)
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


@app.get("/session-info")
async def get_session_info(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Get current user's session information"""
    if current_user.username in active_sessions:
        session = active_sessions[current_user.username]
        return {
            "username": session.username,
            "login_time": session.login_time,
            "last_activity": session.last_activity,
            "session_duration": (datetime.utcnow() - session.login_time).total_seconds() // 60,  # in minutes
            "user_data": session.user_data,
        }
    raise HTTPException(status_code=404, detail="No active session found")


@app.post("/session-data")
async def update_session_data(
    data: Dict[str, Any],
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Update user's session data"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data.update(data)
        active_sessions[current_user.username].last_activity = datetime.utcnow()
        return {"message": "Session data updated", "data": active_sessions[current_user.username].user_data}
    raise HTTPException(status_code=404, detail="No active session found")


# ---------------------------------------------------------------------------
# Protected pages
# ---------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """User dashboard"""
    return templates.TemplateResponse(request, "dashboard.html", {"user": current_user, "ai_ready": ai_available()})


@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Home budget planner page"""
    return templates.TemplateResponse(request, "home_planner.html", {"user": current_user})


@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Party budget planner page"""
    return templates.TemplateResponse(request, "party_planner.html", {"user": current_user})


@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Jewelry budget planner page"""
    return templates.TemplateResponse(request, "jewelry_planner.html", {"user": current_user})


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """History page to view past recommendations"""
    return templates.TemplateResponse(request, "history.html", {"user": current_user})


# ---------------------------------------------------------------------------
# Planner APIs  (/home-budget, /party-budget, /jewelry-budget)
# The /generate-* aliases match the routes named in the project document.
# ---------------------------------------------------------------------------
@app.post("/home-budget")
@app.post("/generate-home")
async def plan_home_budget(
    budget_input: HomeBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Generate home budget recommendations"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_home_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "requirements": {
                "lights": budget_input.num_lights,
                "fans": budget_input.num_fans,
                "furniture": budget_input.num_furniture,
                "dining_tables": budget_input.num_dining_tables,
            },
        }
    if budget_input.num_lights + budget_input.num_fans + budget_input.num_furniture + budget_input.num_dining_tables == 0:
        raise HTTPException(status_code=400, detail="Please enter at least one item (lights, fans, furniture or dining tables).")

    result = await asyncio.to_thread(get_home_recommendations, budget_input)
    result["id"] = save_to_history(current_user.username, "home", budget_input.model_dump(), result)
    return result


@app.post("/party-budget")
@app.post("/generate-party")
async def plan_party_budget(
    budget_input: PartyBudgetInput,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Generate party budget recommendations"""
    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_party_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "party_type": budget_input.party_type,
            "guests": budget_input.num_guests,
        }
    result = await asyncio.to_thread(get_party_recommendations, budget_input)
    result["id"] = save_to_history(current_user.username, "party", budget_input.model_dump(), result)
    return result


@app.post("/jewelry-budget")
@app.post("/generate-jewelry")
async def plan_jewelry_budget(
    request: Request,
    total_budget: float = Form(...),
    occasion: str = Form(...),
    preferences: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Generate jewelry budget recommendations with optional outfit image"""
    if total_budget <= 0:
        raise HTTPException(status_code=400, detail="Budget must be greater than 0")
    budget_input = JewelryBudgetInput(total_budget=total_budget, occasion=occasion, preferences=preferences)

    has_image = image is not None and bool(image.filename)
    image_path = save_upload_file(image) if has_image else None

    if current_user.username in active_sessions:
        active_sessions[current_user.username].user_data["last_jewelry_budget"] = {
            "timestamp": datetime.utcnow().isoformat(),
            "budget": budget_input.total_budget,
            "occasion": budget_input.occasion,
            "has_image": has_image,
        }

    result = await asyncio.to_thread(get_jewelry_recommendations, budget_input, image_path)

    input_data = budget_input.model_dump()
    if image_path:
        input_data["image"] = "/static/uploads/" + os.path.basename(image_path)
        result["outfit_image"] = input_data["image"]
    result["id"] = save_to_history(current_user.username, "jewelry", input_data, result)
    return result


# ---------------------------------------------------------------------------
# History APIs
# ---------------------------------------------------------------------------
@app.get("/recommendation-history")
async def get_recommendation_history(request: Request, current_user: UserInDB = Depends(get_current_active_user)):
    """Get the user's recommendation history"""
    if current_user.username not in user_recommendations:
        return {"history": []}

    # Sort history by timestamp (newest first)
    history = sorted(user_recommendations[current_user.username], key=lambda x: x.timestamp, reverse=True)
    return {
        "history": [
            {
                "id": item.id,
                "timestamp": item.timestamp,
                "type": item.recommendation_type,
                "input": item.input_summary,
                "summary": item.result_summary,
            }
            for item in history
        ]
    }


@app.get("/recommendation-details/{recommendation_id}")
async def get_recommendation_details(
    recommendation_id: str,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Get the full details of a specific recommendation"""
    if current_user.username not in user_recommendations:
        raise HTTPException(status_code=404, detail="No recommendations found")
    for item in user_recommendations[current_user.username]:
        if item.id == recommendation_id:
            return {
                "id": item.id,
                "timestamp": item.timestamp,
                "type": item.recommendation_type,
                "input": item.input_summary,
                "full_result": item.full_result,
            }
    raise HTTPException(status_code=404, detail="Recommendation not found")


@app.delete("/recommendation-details/{recommendation_id}")
async def delete_recommendation(
    recommendation_id: str,
    request: Request,
    current_user: UserInDB = Depends(get_current_active_user),
):
    """Delete a recommendation from history"""
    recs = user_recommendations.get(current_user.username, [])
    remaining = [r for r in recs if r.id != recommendation_id]
    if len(remaining) == len(recs):
        raise HTTPException(status_code=404, detail="Recommendation not found")
    user_recommendations[current_user.username] = remaining
    persist_history()
    return {"message": "Deleted"}


# ---------------------------------------------------------------------------
# Startup: background task to clean up expired sessions
# ---------------------------------------------------------------------------
async def setup_session_cleanup():
    """Background task to clean up expired sessions (runs on /startup)"""

    async def cleanup_expired_sessions():
        while True:
            current_time = datetime.utcnow()
            # Check for sessions that have been inactive for more than 30 minutes
            expired_sessions = [
                username
                for username, session in active_sessions.items()
                if (current_time - session.last_activity).total_seconds() > 1800
            ]
            for username in expired_sessions:
                if username in active_sessions:
                    print(f"Removing expired session for {username}")
                    del active_sessions[username]
            # Wait for 5 minutes before checking again
            await asyncio.sleep(300)

    return asyncio.create_task(cleanup_expired_sessions())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise services and start the session-cleanup task."""
    task = await setup_session_cleanup()
    print(f"PocketSmart started. Gemini AI: {'ENABLED' if ai_available() else 'DISABLED (fallback mode)'}")
    yield
    task.cancel()


app.router.lifespan_context = lifespan


# Main entry point
if __name__ == "__main__":
    import uvicorn

    print("Starting PocketSmart: AI Budget Planner...")
    print("Open http://127.0.0.1:8000 in your browser")
    uvicorn.run(app, host="0.0.0.0", port=8000)
