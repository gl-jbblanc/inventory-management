"""
Tests for the restocking endpoints (recommendations and submitted orders).
"""


def make_item(**overrides):
    item = {
        "sku": "WDG-001",
        "name": "Industrial Widget Type A",
        "quantity": 10,
        "unit_cost": 12.5,
        "lead_time_days": 10,
        "supplier_name": "Apex Components",
    }
    item.update(overrides)
    return item


class TestRestockRecommendations:
    def test_zero_budget_returns_no_items(self, client):
        data = client.get("/api/restocking/recommendations?budget=0").json()
        assert data["items"] == []
        assert data["total_cost"] == 0

    def test_negative_budget_rejected(self, client):
        assert client.get("/api/restocking/recommendations?budget=-1").status_code == 400

    def test_total_never_exceeds_budget(self, client):
        for budget in (500, 5000, 20000, 1000000):
            data = client.get(f"/api/restocking/recommendations?budget={budget}").json()
            assert data["total_cost"] <= budget
            assert data["budget_remaining"] == round(budget - data["total_cost"], 2)

    def test_ranked_by_shortfall_descending(self, client):
        items = client.get("/api/restocking/recommendations?budget=1000000").json()["items"]
        quantities = [i["quantity"] for i in items]
        assert quantities == sorted(quantities, reverse=True)

    def test_stock_on_hand_reduces_shortfall(self, client):
        # PSU-501 forecasts 252 and has 420 on hand, so it needs no restock
        items = client.get("/api/restocking/recommendations?budget=1000000").json()["items"]
        assert "PSU-501" not in [i["sku"] for i in items]

    def test_decreasing_demand_still_needs_stock_without_inventory(self, client):
        # MTR-304 is not in inventory, so its full forecast counts as shortfall
        items = client.get("/api/restocking/recommendations?budget=1000000").json()["items"]
        mtr = next(i for i in items if i["sku"] == "MTR-304")
        assert mtr["quantity"] == 35


class TestRestockOrders:
    def test_submit_order(self, client, restock_storage):
        body = {"budget": 1000, "items": [make_item(), make_item(sku="MTR-304", lead_time_days=21)]}
        response = client.post("/api/restocking/orders", json=body)
        assert response.status_code == 201
        order = response.json()
        assert order["status"] == "Submitted"
        assert order["order_number"].startswith("RST-")
        assert order["total_cost"] == 250.0
        # The slowest item sets the order lead time
        assert order["lead_time_days"] == 21
        assert restock_storage.read_text().count(order["order_number"]) == 1

    def test_empty_order_rejected(self, client, restock_storage):
        assert client.post("/api/restocking/orders", json={"budget": 100, "items": []}).status_code == 400

    def test_over_budget_rejected(self, client, restock_storage):
        body = {"budget": 50, "items": [make_item()]}
        assert client.post("/api/restocking/orders", json=body).status_code == 400
        assert client.get("/api/restocking/orders").json() == []

    def test_non_positive_quantity_rejected(self, client, restock_storage):
        body = {"budget": 1000, "items": [make_item(quantity=0)]}
        assert client.post("/api/restocking/orders", json=body).status_code == 400

    def test_list_returns_newest_first(self, client, restock_storage):
        for _ in range(2):
            client.post("/api/restocking/orders", json={"budget": 1000, "items": [make_item()]})
        numbers = [o["order_number"] for o in client.get("/api/restocking/orders").json()]
        assert len(numbers) == 2
        assert numbers[0] > numbers[1]
