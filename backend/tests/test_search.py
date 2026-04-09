"""
Тесты поиска.
"""


class TestSearch:
    def test_search_returns_dict(self, client):
        r = client.get("/search?q=театр")
        assert r.status_code == 200
        data = r.json()
        assert "query" in data
        assert "results" in data

    def test_search_results_are_list(self, client):
        data = client.get("/search?q=театр").json()
        assert isinstance(data["results"], list)

    def test_search_result_fields(self, client):
        data = client.get("/search?q=театр").json()
        for item in data["results"]:
            assert "entity_type" in item
            assert "id" in item
            assert "title" in item

    def test_search_no_query_param_fails(self, client):
        r = client.get("/search")
        # FastAPI should return 422 (validation error) for missing required param
        assert r.status_code == 422

    def test_search_empty_query_fails(self, client):
        r = client.get("/search?q=")
        assert r.status_code == 422

    def test_search_latin(self, client):
        r = client.get("/search?q=MHAT")
        assert r.status_code == 200
        assert "results" in r.json()
