"""Advancing a test career to its next match day, as a player would: answering any AI club's
bid for one of the user's players on the way (turning it down), since a bid stops the game
(W4-6)."""

from typing import Any

from fastapi.testclient import TestClient


def advance_to_match(client: TestClient) -> dict[str, Any]:
    """POST /api/career/advance until it stops for something other than a bid."""
    for _ in range(50):
        stop: dict[str, Any] = client.post("/api/career/advance").json()
        if stop.get("stop") != "offer":
            return stop
        for bid in client.get("/api/transfers/bids").json():
            client.post(f"/api/transfers/bids/{bid['id']}", json={"action": "reject"})
    raise AssertionError("bids kept stopping the game")


def reject_bids(client: TestClient) -> None:
    for bid in client.get("/api/transfers/bids").json():
        client.post(f"/api/transfers/bids/{bid['id']}", json={"action": "reject"})
