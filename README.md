# PocketSmart AI – Your Smart Budget & Recommendation Assistant

AI-powered budget planner for **Home Interiors**, **Party Planning** and **Jewelry** (with outfit-image analysis),
built with **FastAPI + Google Gemini + Jinja2 (HTML/CSS/JS)**.

> A printable version of this setup guide is also available: **[documentation/PocketSmart_AI_Setup_Guide.docx](documentation/PocketSmart_AI_Setup_Guide.docx)**

---

## 1. Requirements
- Windows 10 or 11 with an internet connection
- Python 3.12 (3.10 to 3.12 also work)
- Git
- A Google Gemini API key (free from Google AI Studio)

## 2. Install Python and Git (one time only)

### 2.1 Install Python
1. Download from **https://www.python.org/downloads/windows** (Windows installer, 64-bit).
2. On the first installer screen, tick **"Add python.exe to PATH"**. This is very important.
3. Click **Install Now** and wait for it to finish.

### 2.2 Install Git
1. Download from **https://git-scm.com/download/win**.
2. Run the installer and keep clicking **Next** (default options are fine).

### 2.3 Check the installation
Close any open terminal, open a new Command Prompt, and run:
```
python --version
git --version
```
Both commands should print a version number.

## 3. Clone the Project
```
cd %USERPROFILE%\Desktop
git clone https://github.com/gopiaarthi254/Pocket-Smart-AI.git
cd Pocket-Smart-AI
```

## 4. Create a Virtual Environment and Install Packages
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```
When the environment is active, you will see **(venv)** at the start of the terminal line.

## 5. Create the `.env` File (API Key)
The `.env` file is not stored on GitHub because it contains your secret key. Create it on every new computer:
```
copy .env.example .env
notepad .env
```
In Notepad, fill in the values and save with **Ctrl + S**:
```
GOOGLE_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
SECRET_KEY=any_long_random_text
ACCESS_TOKEN_EXPIRE_MINUTES=30
```
Get a free Gemini API key at **https://aistudio.google.com/app/apikey**. Do not add spaces or quotes around the key.

> **Note:** Keep your API key private. Never upload the `.env` file to GitHub or share it with others.

## 6. Run the Application
```
python app.py
```
The terminal should show **"Gemini AI: ENABLED"**. Then open this address in your browser:
```
http://127.0.0.1:8000
```
1. Click **Get Started** and register a new account (accounts are stored separately on each computer).
2. Log in and open the Home, Party or Jewelry planner.
3. Enter your budget and click Generate. Results with a green **"Gemini AI"** badge come from Gemini.

To stop the server, press **Ctrl + C** in the terminal.

> Without an API key the app still runs and shows rule-based **default recommendations**, marked with an
> orange "Default plan" badge.

## 7. Running Again Next Time
After the first setup, only these commands are needed:
```
cd %USERPROFILE%\Desktop\Pocket-Smart-AI
venv\Scripts\activate
python app.py
```

## 8. Getting the Latest Changes from GitHub
```
git pull
pip install -r requirements.txt
```

## 9. Common Problems and Fixes
| Problem | Fix |
|---|---|
| `python` or `git` is not recognized | Reinstall (tick "Add python.exe to PATH" for Python) and open a new terminal. You can also try `py` instead of `python`. |
| "running scripts is disabled" when activating venv | Use Command Prompt instead of PowerShell, or run once in PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Orange "Default plan" badge instead of "Gemini AI" | Check that `.env` exists and the key is correct, then restart `python app.py`. The terminal prints the reason on a line starting with `[PocketSmart]`. |
| "Address already in use" / port 8000 busy | The app is already running in another terminal. Close it or press Ctrl + C there first. |
| `pip install` fails | Check your internet connection, then run `python -m pip install --upgrade pip` and try again. |
| Page looks old after an update | Press **Ctrl + F5** in the browser to clear the cached style. |

## 10. Project Structure
```
Pocket-Smart-AI/
├── app.py              FastAPI app: routes, login, sessions, history
├── gemini_utils.py     Gemini AI, prompts, shopping links, fallback plans
├── models.py           Input/output data models (Pydantic)
├── requirements.txt    Python packages
├── .env.example        Template for the .env file
├── documentation/      PocketSmart_AI_Setup_Guide.docx (printable setup guide)
├── static/             styles.css, script.js, uploads/
├── templates/          HTML pages (Jinja2)
└── data/               users.json + history.json (created automatically, not on GitHub)
```

---

## Routes (as per the project document)
| Route | Method | Purpose |
|---|---|---|
| `/` | GET | Landing page |
| `/register`, `/login` | GET/POST | Registration & login pages |
| `/token` | POST | Issues JWT (stored in an HTTP-only cookie) |
| `/logout` | GET/POST | Blacklists token, clears session |
| `/dashboard` | GET | User dashboard with recent activity |
| `/home-planner`, `/party-planner`, `/jewelry-planner` | GET | Planner pages |
| `/home-budget` (alias `/generate-home`) | POST | Home interior recommendations |
| `/party-budget` (alias `/generate-party`) | POST | Party recommendations |
| `/jewelry-budget` (alias `/generate-jewelry`) | POST | Jewelry recommendations (text + optional image) |
| `/recommendation-history` | GET | User's past recommendations |
| `/recommendation-details/{id}` | GET/DELETE | Full details of one recommendation |
| `/history` | GET | History page |
| `/session-info`, `/session-data` | GET/POST | Session metadata / personalization data |
| `/docs` | GET | Auto-generated Swagger API docs |

## Notes
- **Gemini model:** the project document specifies *Gemini 1.5 Flash*. Google has retired the 1.5 models, so the
  app uses `gemini-2.5-flash` by default (set `GEMINI_MODEL` in `.env` to change it). It automatically tries newer
  Flash models if one isn't available.
- **Product data:** real e-commerce APIs are not called (Activity 3.4). Gemini suggests products with INR prices,
  and the app builds search links for Amazon, Flipkart, IKEA, Pepperfry, Swiggy, Zomato, OYO, MakeMyTrip,
  BookMyShow, Tanishq, CaratLane, BlueStone, Melorra, Meesho and more.
- **Budget adherence (Milestone 5):** totals, the allocation table and the remaining budget are recalculated on the
  server from the actual items, and the UI warns if a plan exceeds the budget.
- **Error handling:** input validation on both frontend and backend; if Gemini fails or returns bad JSON, the
  fallback plan is shown instead of an error.
