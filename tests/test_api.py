import pytest

import app as app_module


@pytest.fixture
def client():
    app_module.app.config["TESTING"] = True
    return app_module.app.test_client()


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200 and response.get_json() == {"status": "ok"}


def test_review_success(client):
    response = client.post("/api/review", json={"code": "x = 1", "language": "Python"})
    assert response.status_code == 200
    assert 0 <= response.get_json()["score"] <= 10


@pytest.mark.parametrize(
    "body",
    [
        {"code": "", "language": "python"},
        {"code": "   ", "language": "python"},
        {"language": "python"},
        {"code": "x = 1", "language": "cobol"},
        {"code": "x = 1"},
        {"code": "x" * (app_module.MAX_CODE_LENGTH + 1), "language": "python"},
    ],
)
def test_invalid_input_returns_400(client, body):
    response = client.post("/api/review", json=body)
    assert response.status_code == 400 and "error" in response.get_json()


@pytest.mark.parametrize(
    "body",
    [
        {"code": 123, "language": "python"},
        {"code": "x = 1", "language": ["python"]},
        [1, 2, 3],
        "just a string",
        None,
    ],
)
def test_wrong_types_return_400_not_500(client, body):
    # Regression: non-string fields and non-object bodies used to raise a 500.
    assert client.post("/api/review", json=body).status_code == 400


def test_non_json_body_returns_400(client):
    response = client.post("/api/review", data="not json", content_type="text/plain")
    assert response.status_code == 400


def test_code_at_limit_is_accepted(client):
    code = "x" * app_module.MAX_CODE_LENGTH
    assert client.post("/api/review", json={"code": code, "language": "python"}).status_code == 200
