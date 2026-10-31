import pytest

from app import DATA_FILE, create_app, load_items, read_release

ITEMS = {
    1: {"id": 1, "name": "Server", "category": "compute", "quantity": 4, "location": "A"},
    2: {"id": 2, "name": "Switch", "category": "network", "quantity": 2, "location": "A"},
    3: {"id": 3, "name": "Optic", "category": "network", "quantity": 30, "location": "B"},
}
RELEASE = {"release": "00007-abc1234", "commit": "abc1234def", "built": "2026-01-01T00:00:00Z"}


@pytest.fixture
def client():
    app = create_app(items=ITEMS, release=RELEASE)
    app.config["TESTING"] = True
    return app.test_client()


def test_health_reports_release(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["release"] == "00007-abc1234"
    assert body["commit"] == "abc1234def"


def test_index_lists_endpoints(client):
    body = client.get("/").get_json()
    assert body["service"] == "inventory-api"
    assert "/health" in body["endpoints"]


def test_list_items_sorted(client):
    body = client.get("/api/items").get_json()
    assert body["count"] == 3
    assert [i["id"] for i in body["items"]] == [1, 2, 3]


def test_filter_by_category_is_case_insensitive(client):
    body = client.get("/api/items?category=NETWORK").get_json()
    assert body["count"] == 2
    assert {i["id"] for i in body["items"]} == {2, 3}


def test_filter_low_stock(client):
    body = client.get("/api/items?low_stock=4").get_json()
    assert {i["id"] for i in body["items"]} == {1, 2}


def test_low_stock_must_be_integer(client):
    resp = client.get("/api/items?low_stock=lots")
    assert resp.status_code == 400
    assert resp.get_json()["message"] == "low_stock must be an integer"


def test_get_item(client):
    resp = client.get("/api/items/2")
    assert resp.status_code == 200
    assert resp.get_json()["name"] == "Switch"


def test_unknown_item_is_json_404(client):
    resp = client.get("/api/items/99")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "Not Found"


def test_unknown_route_is_json_404(client):
    resp = client.get("/nope")
    assert resp.status_code == 404
    assert resp.is_json


def test_shipped_catalogue_is_valid():
    items = load_items(DATA_FILE)
    assert items, "catalogue must not be empty"
    for item_id, item in items.items():
        assert item_id == item["id"]
        assert {"name", "category", "quantity", "location"} <= set(item)
        assert isinstance(item["quantity"], int) and item["quantity"] >= 0


def test_read_release_parses_pipeline_file(tmp_path):
    f = tmp_path / "RELEASE"
    f.write_text(
        "release=00009-feed123\ncommit=feed123\n"
        "built=2026-02-02T00:00:00Z\nextra=ignored\n"
    )
    assert read_release(f) == {
        "release": "00009-feed123",
        "commit": "feed123",
        "built": "2026-02-02T00:00:00Z",
    }


def test_read_release_defaults_when_missing(tmp_path):
    assert read_release(tmp_path / "missing")["release"] == "dev"
