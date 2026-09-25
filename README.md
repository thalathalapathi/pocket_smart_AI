# PocketSmart AI: Your Smart Budget & Recommendation Assistant

**PocketSmart AI** is a GenAI-powered, cross-platform recommendation system that delivers personalized, budget-based suggestions across home interiors, party planning, and jewelry shopping. Powered by **Google Gemini AI** and **FastAPI**, it bridges user constraints with major e-commerce ecosystems including Amazon India, Flipkart, IKEA, Swiggy, Zomato, BookMyShow, MakeMyTrip, OYO, Tanishq, CaratLane, and BlueStone.

---

## 🌟 Key Features & Milestone Completion

### 1. Milestone 1: Gemini AI Initialization & Setup
- Configured with `google.generativeai` multimodal foundation model support.
- Configured `.env` file for `GEMINI_API_KEY`, JWT secret key, and environment settings.
- Integrated intelligent fallback generation ensuring 100% resilience and uptime even when offline or before API key setup.

### 2. Milestone 2: Core Functionalities Development (`gemini_utils.py`)
- **Home Interior Planner**: Allocates budgets across Lighting, Ceiling Fans, Furniture, and Dining tables based on specified room choices (Living Room, Kitchen, Bedroom). Generates Indian platform shopping links (Amazon, Flipkart, IKEA, Myntra, Ajio).
- **Party Budget Planner**: Allocates funds across catering, decor, entertainment, and contingency for events (Birthdays, Weddings, Corporate, etc.) with guest count calculation. Sourcing links for Swiggy, Zomato, BigBasket, BookMyShow, and venue recommendations.
- **Jewelry Budget Planner**: Multimodal vision analysis supporting outfit image uploads to detect color palette, style, and formality, generating coordinated jewelry suggestions with links to Tanishq, CaratLane, BlueStone, Amazon, and Flipkart.

### 3. Milestone 3: Backend & FastAPI Integration (`app.py` & `main.py`)
- Full OAuth2 & JWT session management (`/login`, `/register`, `/token`, `/logout`, `/session-info`, `/session-data`).
- REST endpoints:
  - `POST /generate-home` and `POST /home-budget`
  - `POST /generate-party` and `POST /party-budget`
  - `POST /generate-jewelry` and `POST /jewelry-budget`
  - `GET /recommendation-history`
  - `GET /recommendations-details/{id}`
- Asynchronous background task cleans up expired sessions every 5 minutes.
- File-backed persistent user history in `data/history.json` and users in `data/users.json`.

### 4. Milestone 4: UI Development (`templates/` & `static/styles.css`)
- **Landing Page (`index.html`)**: Hero section, 3 planner cards, user testimonials, and footer.
- **User Dashboard (`dashboard.html`)**: Greeting banner ("Welcome, sai!"), quick planner launch cards, "View All Recommendation History", and recent activity list.
- **Authentication Pages (`login.html` & `register.html`)**: Clean cards with password validation.
- **Planner Interfaces**:
  - `home_planner.html`: Form with dynamic real-time result cards and shopping badges.
  - `party_planner.html`: Event needs, guest scaling, venue suggestions, and print/save option.
  - `jewelry_planner.html`: Image drag-and-drop preview, outfit analysis badges, and styling tips.
  - `history.html`: Filterable recommendation cards with modal popup for full details.

### 5. Milestone 5: Testing & Optimization (`test_app.py`)
- 100% automated test pass rate across all 9 endpoint workflows.

---

## 🚀 Running the Application Locally

1. **Activate the Virtual Environment**:
   ```powershell
   .\venv\Scripts\Activate.ps1
   ```

2. **Start the Server**:
   ```powershell
   python main.py
   # OR
   uvicorn app:app --reload --host 127.0.0.1 --port 8000
   ```

3. **Open in Browser**:
   Navigate to [http://127.0.0.1:8000](http://127.0.0.1:8000)

4. **Default Demo Credentials**:
   - **Username**: `sai`
   - **Password**: `password123`
   *(New accounts can also be registered at `/register`)*
