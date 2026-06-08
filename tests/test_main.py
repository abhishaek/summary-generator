async def test_health_returns_200(client):
    response = await client.get("/health")
    assert response.status_code == 200


async def test_health_returns_correct_body(client):
    response = await client.get("/health")
    assert response.json() == {"status": "I am Healthy!"}
