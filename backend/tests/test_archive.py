"""
Тесты архивной структуры: фонды, описи, дела.
"""
import pytest
import time


# ─────────────────────────────────────────────────────────────
# ФОНДЫ
# ─────────────────────────────────────────────────────────────

class TestFunds:
    def test_list_funds_returns_list(self, client):
        r = client.get("/archive/funds")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)

    def test_funds_have_required_fields(self, client):
        data = client.get("/archive/funds").json()
        if data:
            f = data[0]
            assert "id" in f
            assert "code" in f
            assert "name" in f


# ─────────────────────────────────────────────────────────────
# ОПИСИ
# ─────────────────────────────────────────────────────────────

class TestInventories:
    def test_list_inventories(self, client):
        r = client.get("/archive/inventories")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_inventories_have_required_fields(self, client):
        data = client.get("/archive/inventories").json()
        if data:
            inv = data[0]
            for field in ("id", "title", "number", "fund_code", "cases_count"):
                assert field in inv, f"missing field: {field}"

    def test_get_inventory_by_id(self, client):
        inventories = client.get("/archive/inventories").json()
        if not inventories:
            pytest.skip("no inventories in DB")
        inv_id = inventories[0]["id"]
        r = client.get(f"/archive/inventories/{inv_id}")
        assert r.status_code == 200
        data = r.json()
        assert "inventory" in data
        assert "cases" in data
        assert data["inventory"]["id"] == inv_id

    def test_get_inventory_404(self, client):
        r = client.get("/archive/inventories/999999999")
        assert r.status_code == 200          # API returns 200 with error field
        assert "error" in r.json()

    def test_inventory_cases_have_effective_dates(self, client):
        inventories = client.get("/archive/inventories").json()
        if not inventories:
            pytest.skip("no inventories")
        inv_id = inventories[0]["id"]
        cases = client.get(f"/archive/inventories/{inv_id}").json()["cases"]
        # effective_date_from / effective_date_to may be None but fields must exist
        for c in cases:
            assert "effective_date_from" in c
            assert "effective_date_to" in c


# ─────────────────────────────────────────────────────────────
# ДЕЛА  (CRUD + show_on_site)
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def inventory_id(client):
    """Returns the id of the first available inventory, or skips."""
    inventories = client.get("/archive/inventories").json()
    if not inventories:
        pytest.skip("no inventories in DB")
    return inventories[0]["id"]


class TestCases:
    """CRUD lifecycle for a single test case (self-cleaning via cleanup fixture)."""

    def test_create_case(self, client, cleanup, inventory_id):
        payload = {
            "inventory_id": inventory_id,
            "number": f"TEST{int(time.time())}",
            "title": "__TEST__ тестовое дело",
            "description": "автотест — удалить",
            "project_group": "Тестовая группа",
        }
        r = client.post("/archive/cases", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "id" in data
        cleanup["cases"].append(data["id"])
        self.__class__._case_id = data["id"]

    def test_get_created_case(self, client):
        case_id = self.__class__._case_id
        r = client.get(f"/archive/cases/{case_id}")
        assert r.status_code == 200
        data = r.json()
        assert "case" in data
        assert data["case"]["id"] == case_id
        assert data["case"]["title"] == "__TEST__ тестовое дело"
        assert "units" in data
        assert "productions" in data

    def test_case_has_show_on_site_field(self, client):
        case_id = self.__class__._case_id
        data = client.get(f"/archive/cases/{case_id}").json()
        # show_on_site comes from inventory list, not from case detail directly
        # but we can verify via inventory
        inv_data = client.get(f"/archive/inventories/{data['case']['inventory_id']}").json()
        case_in_inv = next((c for c in inv_data["cases"] if c["id"] == case_id), None)
        assert case_in_inv is not None
        assert "show_on_site" in case_in_inv

    def test_update_case(self, client):
        case_id = self.__class__._case_id
        r = client.get(f"/archive/cases/{case_id}").json()
        inv_id = r["case"]["inventory_id"]
        payload = {
            "inventory_id": inv_id,
            "title": "__TEST__ обновлённое дело",
            "description": "обновлено",
            "project_group": "Новая группа",
        }
        r2 = client.put(f"/archive/cases/{case_id}", json=payload)
        assert r2.status_code == 200
        assert r2.json().get("status") == "ok"
        # Verify update persisted
        updated = client.get(f"/archive/cases/{case_id}").json()
        assert updated["case"]["title"] == "__TEST__ обновлённое дело"

    def test_toggle_case_show_on_site_true(self, client):
        case_id = self.__class__._case_id
        r = client.patch(f"/archive/cases/{case_id}/show-on-site?show=true")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_toggle_case_show_on_site_false(self, client):
        case_id = self.__class__._case_id
        r = client.patch(f"/archive/cases/{case_id}/show-on-site?show=false")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_get_case_404(self, client):
        r = client.get("/archive/cases/999999999")
        assert r.status_code == 200
        assert "error" in r.json()
