"""
Тесты персон: CRUD.
"""
import pytest


class TestPersons:
    def test_list_persons(self, client):
        r = client.get("/persons")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_persons_pagination(self, client):
        r = client.get("/persons?limit=2&offset=0")
        assert r.status_code == 200
        assert len(r.json()) <= 2

    def test_create_person(self, client, cleanup):
        payload = {
            "last_name": "__TEST__",
            "first_name": "Иван",
            "patronymic": "Тестович",
            "roles": ["режиссёр", "актёр"],
            "bio": "Тестовая биография",
        }
        r = client.post("/persons", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert data.get("status") == "ok"
        assert "id" in data
        cleanup["persons"].append(data["id"])
        self.__class__._person_id = data["id"]

    def test_get_person(self, client):
        pid = self.__class__._person_id
        r = client.get(f"/persons/{pid}")
        assert r.status_code == 200
        data = r.json()
        assert "person" in data
        assert data["person"]["last_name"] == "__TEST__"
        assert "productions" in data
        assert "documents" in data

    def test_person_has_roles(self, client):
        pid = self.__class__._person_id
        person = client.get(f"/persons/{pid}").json()["person"]
        assert person["roles"] == ["режиссёр", "актёр"]

    def test_update_person(self, client):
        pid = self.__class__._person_id
        payload = {
            "last_name": "__TEST__",
            "first_name": "Пётр",
            "roles": ["продюсер"],
            "bio": "Обновлённая биография",
        }
        r = client.put(f"/persons/{pid}", json=payload)
        assert r.status_code == 200
        assert r.json().get("status") == "ok"
        updated = client.get(f"/persons/{pid}").json()["person"]
        assert updated["first_name"] == "Пётр"

    def test_get_person_404(self, client):
        r = client.get("/persons/999999999")
        assert r.status_code == 200
        assert "error" in r.json()
