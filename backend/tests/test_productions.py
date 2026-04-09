"""
Тесты спектаклей: CRUD, связь с персонами, show_on_site.
"""
import pytest
import time


@pytest.fixture(scope="module")
def test_person_id(client, cleanup):
    """Вспомогательная персона для добавления в спектакль."""
    r = client.post("/persons", json={"last_name": "__TEST__P", "first_name": "Вспомогательный"})
    pid = r.json()["id"]
    cleanup["persons"].append(pid)
    return pid


@pytest.fixture(scope="module")
def inventory_id(client):
    inventories = client.get("/archive/inventories").json()
    if not inventories:
        pytest.skip("no inventories in DB")
    return inventories[0]["id"]


@pytest.fixture(scope="module")
def test_case_id(client, cleanup, inventory_id):
    r = client.post("/archive/cases", json={
        "inventory_id": inventory_id,
        "number": f"TEST{int(time.time())}",
        "title": "__TEST__ дело для спектаклей",
    })
    cid = r.json()["id"]
    cleanup["cases"].append(cid)
    return cid


class TestProductions:
    def test_list_productions(self, client):
        r = client.get("/productions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_productions_pagination(self, client):
        r = client.get("/productions?limit=3&offset=0")
        assert r.status_code == 200
        assert len(r.json()) <= 3

    def test_create_production(self, client, cleanup, test_case_id):
        payload = {
            "title": "__TEST__ Тестовый спектакль",
            "subtitle": "Подзаголовок",
            "playwright": "Чехов А.П.",
            "genre": "драма",
            "season": "2024/25",
            "premiere_date": "2024-10-01",
            "theater_name": "Тестовый театр",
            "description": "Описание для автотеста",
            "inventory_case_id": test_case_id,
        }
        r = client.post("/productions", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "id" in data
        cleanup["productions"].append(data["id"])
        self.__class__._prod_id = data["id"]

    def test_get_production(self, client):
        pid = self.__class__._prod_id
        r = client.get(f"/productions/{pid}")
        assert r.status_code == 200
        data = r.json()
        assert "production" in data
        assert data["production"]["title"] == "__TEST__ Тестовый спектакль"
        assert data["production"]["playwright"] == "Чехов А.П."
        assert "persons" in data
        assert "documents" in data

    def test_update_production(self, client, test_case_id):
        pid = self.__class__._prod_id
        payload = {
            "title": "__TEST__ Обновлённый спектакль",
            "playwright": "Достоевский Ф.М.",
            "genre": "трагедия",
            "theater_name": "Тестовый театр",
            "inventory_case_id": test_case_id,
        }
        r = client.put(f"/productions/{pid}", json=payload)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
        updated = client.get(f"/productions/{pid}").json()["production"]
        assert updated["title"] == "__TEST__ Обновлённый спектакль"
        assert updated["playwright"] == "Достоевский Ф.М."

    def test_toggle_production_show_on_site_true(self, client):
        pid = self.__class__._prod_id
        r = client.patch(f"/productions/{pid}/show-on-site?show=true")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_production_appears_in_site_data(self, client):
        """После включения show_on_site спектакль должен быть в /site/data."""
        pid = self.__class__._prod_id
        site_data = client.get("/site/data").json()
        ids = [item["id"] for item in site_data if item.get("item_type") == "production"]
        assert pid in ids

    def test_toggle_production_show_on_site_false(self, client):
        pid = self.__class__._prod_id
        r = client.patch(f"/productions/{pid}/show-on-site?show=false")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_production_not_in_site_data_after_disable(self, client):
        pid = self.__class__._prod_id
        site_data = client.get("/site/data").json()
        ids = [item["id"] for item in site_data if item.get("item_type") == "production"]
        assert pid not in ids

    def test_add_person_to_production(self, client, test_person_id):
        pid = self.__class__._prod_id
        r = client.post(f"/productions/{pid}/persons",
                        json={"person_id": test_person_id, "role_in_production": "режиссёр"})
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_person_appears_in_production(self, client, test_person_id):
        pid = self.__class__._prod_id
        persons = client.get(f"/productions/{pid}").json()["persons"]
        person_ids = [p["id"] for p in persons]
        assert test_person_id in person_ids

    def test_remove_person_from_production(self, client, test_person_id):
        pid = self.__class__._prod_id
        r = client.delete(f"/productions/{pid}/persons/{test_person_id}")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_person_removed_from_production(self, client, test_person_id):
        pid = self.__class__._prod_id
        persons = client.get(f"/productions/{pid}").json()["persons"]
        person_ids = [p["id"] for p in persons]
        assert test_person_id not in person_ids

    def test_production_visible_in_case(self, client, test_case_id):
        """Спектакль должен быть в списке productions у дела."""
        pid = self.__class__._prod_id
        case_data = client.get(f"/archive/cases/{test_case_id}").json()
        prod_ids = [p["id"] for p in case_data["productions"]]
        assert pid in prod_ids

    def test_get_production_404(self, client):
        r = client.get("/productions/999999999")
        assert r.status_code == 200
        assert "error" in r.json()
