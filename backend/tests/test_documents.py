"""
Тесты документов: загрузка, show_on_site, привязка к делу.
"""
import pytest
import io
import time


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
        "title": "__TEST__ дело для документов",
    })
    cid = r.json()["id"]
    cleanup["cases"].append(cid)
    return cid


class TestDocuments:
    def test_list_documents(self, client):
        r = client.get("/documents")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_doc_types(self, client):
        r = client.get("/doc-types")
        assert r.status_code == 200
        types = r.json()
        assert isinstance(types, list)
        assert "фотография" in types
        assert "другое" in types

    def test_upload_document(self, client, cleanup, test_case_id):
        """Загружаем минимальный текстовый файл как документ."""
        fake_file = io.BytesIO(b"test content for theatre archive")
        fake_file.name = "test_doc.txt"
        r = client.post(
            "/upload/document",
            data={
                "title": "__TEST__ тестовый документ",
                "doc_type": "другое",
                "description": "автотест",
                "case_id": str(test_case_id),
            },
            files={"file": ("test_doc.txt", fake_file, "text/plain")},
        )
        assert r.status_code == 200
        data = r.json()
        assert "doc_id" in data or "id" in data
        doc_id = data.get("doc_id") or data.get("id")
        assert doc_id
        cleanup["documents"].append(doc_id)
        self.__class__._doc_id = doc_id

    def test_get_document(self, client):
        doc_id = self.__class__._doc_id
        r = client.get(f"/documents/{doc_id}")
        assert r.status_code == 200
        data = r.json()
        assert "document" in data
        assert data["document"]["title"] == "__TEST__ тестовый документ"

    def test_document_appears_in_case(self, client, test_case_id):
        """Загруженный документ должен быть в единицах хранения дела."""
        doc_id = self.__class__._doc_id
        case_data = client.get(f"/archive/cases/{test_case_id}").json()
        doc_ids = [u.get("doc_id") for u in case_data["units"] if u.get("object_type") == "document"]
        assert doc_id in doc_ids

    def test_document_unit_has_show_on_site_field(self, client, test_case_id):
        """Каждая единица хранения должна иметь поле show_on_site."""
        case_data = client.get(f"/archive/cases/{test_case_id}").json()
        for unit in case_data["units"]:
            if unit.get("object_type") == "document":
                assert "show_on_site" in unit

    def test_toggle_document_show_on_site_true(self, client):
        doc_id = self.__class__._doc_id
        r = client.patch(f"/documents/{doc_id}/show-on-site?show=true")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_document_appears_in_site_data(self, client):
        doc_id = self.__class__._doc_id
        site_data = client.get("/site/data").json()
        ids = [item["id"] for item in site_data if item.get("item_type") == "document"]
        assert doc_id in ids

    def test_toggle_document_show_on_site_false(self, client):
        doc_id = self.__class__._doc_id
        r = client.patch(f"/documents/{doc_id}/show-on-site?show=false")
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

    def test_document_not_in_site_data_after_disable(self, client):
        doc_id = self.__class__._doc_id
        site_data = client.get("/site/data").json()
        ids = [item["id"] for item in site_data if item.get("item_type") == "document"]
        assert doc_id not in ids

    def test_get_document_404(self, client):
        r = client.get("/documents/999999999")
        assert r.status_code == 200
        assert "error" in r.json()
