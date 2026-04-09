"""
Тесты публичного сайта: /site/config, /site/data.
"""


class TestSiteConfig:
    def test_get_site_config(self, client):
        r = client.get("/site/config")
        assert r.status_code == 200
        cfg = r.json()
        assert isinstance(cfg, dict)

    def test_update_site_config(self, client):
        """Обновляем поле, сохраняем старое значение, восстанавливаем."""
        original = client.get("/site/config").json()
        old_tagline = original.get("hero_tagline", "")

        r = client.put("/site/config", json={"hero_tagline": "__TEST_TAGLINE__"})
        assert r.status_code == 200
        assert r.json().get("status") == "ok"

        updated = client.get("/site/config").json()
        assert updated["hero_tagline"] == "__TEST_TAGLINE__"

        # Restore
        client.put("/site/config", json={"hero_tagline": old_tagline})

    def test_site_config_hero_fields_exist(self, client):
        cfg = client.get("/site/config").json()
        for key in ("hero_title", "hero_tagline"):
            assert key in cfg, f"missing site_config key: {key}"


class TestSiteData:
    def test_get_site_data(self, client):
        r = client.get("/site/data")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_site_data_items_have_type(self, client):
        """Каждый элемент должен иметь item_type: production или document."""
        data = client.get("/site/data").json()
        for item in data:
            assert item.get("item_type") in ("production", "document"), \
                f"unexpected item_type: {item.get('item_type')}"

    def test_site_data_items_have_hierarchy(self, client):
        """Все элементы имеют ссылку на опись и дело."""
        data = client.get("/site/data").json()
        for item in data:
            assert "inventory_id" in item
            assert "inventory_title" in item
            assert "case_id" in item
            assert "case_title" in item
