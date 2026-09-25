import httpx
import sys
from app import app
from fastapi.testclient import TestClient

def test_pocketsmart_application():
    client = TestClient(app)
    
    print("Testing 1: Landing Page GET /")
    res = client.get("/")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}"
    assert "PocketSmart" in res.text
    print("[PASS] Landing page returned 200 with PocketSmart branding.")

    print("\nTesting 2: Login Page GET /login")
    res = client.get("/login")
    assert res.status_code == 200
    assert "Welcome Back" in res.text
    print("[PASS] Login page returned 200.")

    print("\nTesting 3: Login Authentication POST /login")
    login_data = {"username": "sai", "password": "password123"}
    res = client.post("/login", data=login_data, follow_redirects=False)
    assert res.status_code == 302, f"Expected 302 redirect, got {res.status_code}"
    assert res.headers.get("location") == "/dashboard"
    cookie = res.cookies.get("access_token")
    assert cookie is not None, "Access token cookie was not set"
    print("[PASS] Login succeeded with 302 redirect and access_token cookie.")

    print("\nTesting 4: Dashboard Page GET /dashboard with Auth Cookie")
    res = client.get("/dashboard", cookies={"access_token": cookie})
    assert res.status_code == 200
    assert "Welcome, sai!" in res.text
    print("[PASS] Dashboard returned 200 with 'Welcome, sai!'.")

    print("\nTesting 5: Session Info GET /session-info")
    res = client.get("/session-info", cookies={"access_token": cookie})
    assert res.status_code == 200
    s_info = res.json()
    assert s_info["username"] == "sai"
    print(f"[PASS] Session info returned: {s_info['username']}")

    print("\nTesting 6: Home Interior Planner GET /home-planner and POST /generate-home")
    res = client.get("/home-planner", cookies={"access_token": cookie})
    assert res.status_code == 200
    home_payload = {
        "total_budget": 5000,
        "num_lights": 5,
        "num_fans": 4,
        "num_furniture": 2,
        "num_dining_tables": 1,
        "has_living_room": True,
        "has_kitchen": True,
        "has_bedroom": False,
        "additional_requirements": "Modern compact style"
    }
    res = client.post("/generate-home", json=home_payload, cookies={"access_token": cookie})
    assert res.status_code == 200
    home_res = res.json()
    assert "budget_breakdown" in home_res
    assert "remaining_budget" in home_res
    print(f"[PASS] Home recommendations generated with {len(home_res['budget_breakdown'])} categories and shopping links.")

    print("\nTesting 7: Party Budget Planner GET /party-planner and POST /generate-party")
    res = client.get("/party-planner", cookies={"access_token": cookie})
    assert res.status_code == 200
    party_payload = {
        "total_budget": 5000,
        "num_guests": 3,
        "party_type": "Wedding",
        "venue_type": "Home",
        "needs_catering": True,
        "needs_decoration": True,
        "needs_entertainment": True,
        "additional_requirements": "Vegetarian buffet"
    }
    res = client.post("/generate-party", json=party_payload, cookies={"access_token": cookie})
    assert res.status_code == 200
    party_res = res.json()
    assert "budget_breakdown" in party_res
    assert "venue_suggestions" in party_res
    print(f"[PASS] Party recommendations generated with {len(party_res['budget_breakdown'])} categories.")

    print("\nTesting 8: Jewelry Budget Planner GET /jewelry-planner and POST /generate-jewelry")
    res = client.get("/jewelry-planner", cookies={"access_token": cookie})
    assert res.status_code == 200
    jewelry_form = {
        "total_budget": "5000",
        "occasion": "Birthday",
        "preferences": "Minimalist silver or rose gold"
    }
    res = client.post("/generate-jewelry", data=jewelry_form, cookies={"access_token": cookie})
    assert res.status_code == 200
    jewelry_res = res.json()
    assert "jewelry_recommendations" in jewelry_res
    print(f"[PASS] Jewelry recommendations generated with {len(jewelry_res['jewelry_recommendations'])} items.")

    print("\nTesting 9: History GET /history and GET /recommendation-history")
    res = client.get("/history", cookies={"access_token": cookie})
    assert res.status_code == 200
    res = client.get("/recommendation-history", cookies={"access_token": cookie})
    assert res.status_code == 200
    hist_json = res.json()
    assert len(hist_json["history"]) > 0
    print(f"[PASS] Recommendation history retrieved with {len(hist_json['history'])} entries.")

    first_id = hist_json["history"][0]["id"]
    res = client.get(f"/recommendations-details/{first_id}", cookies={"access_token": cookie})
    assert res.status_code == 200
    print(f"[PASS] Recommendation details for {first_id} verified successfully.")

    print("\n==========================================")
    print("ALL TESTS PASSED WITH 100% SUCCESS!")
    print("==========================================")

if __name__ == "__main__":
    test_pocketsmart_application()
