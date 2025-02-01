import aiosqlite
import pytest
from aiohttp import web
import script
from script import app, clean_db, cleanup_periodic_weather_update, routes, init_db, start_periodic_weather_update  
from datetime import datetime


DATABASE = "test.db"

@pytest.fixture
async def setup_test_db(monkeypatch):
    monkeypatch.setattr('script.DATABASE', DATABASE)
    return DATABASE


@pytest.fixture
def app():
    app = web.Application()
    app.add_routes(routes)
    app.on_startup.append(clean_db)
    app.on_startup.append(init_db)
    app.on_startup.append(start_periodic_weather_update)
    app.on_cleanup.append(cleanup_periodic_weather_update)
    return app



class Test_weather:

    async def test_fetch_weather_invalid_coordinates(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)

        resp = await client.get('/weather?latitude=abc&longitude=xyz')
        assert resp.status == 400
        data = await resp.json()

        assert 'error' in data

    async def test_fetch_weather_missing_params(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        resp = await client.get('/weather')
        assert resp.status == 400
        data = await resp.json()
        assert 'error' in data

    async def test_fetch_weather_best_case(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        resp = await client.get('/weather?latitude=14&longitude=50')
        assert resp.status == 200
        data = await resp.json()
        assert all([res in data for res in ['temperature', 'wind_speed', 'pressure']])



class Test_add_city:

    async def test_add_city_success_without_user(self, aiohttp_client, app, setup_test_db):
        payload = {
            "name": "Test City",
            "latitude": 12.34,
            "longitude": 56.78
        }
        client = await aiohttp_client(app)
        resp = await client.post('/city', json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert "message" in data
        assert "Test City" in data["message"]

        async with aiosqlite.connect(setup_test_db) as db:
            cursor = await db.execute('SELECT name, latitude, longitude FROM cities WHERE name = ?', (payload["name"],))
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == payload["name"]
            assert row[1] == payload["latitude"]
            assert row[2] == payload["longitude"]

    
    async def test_add_city_success_with_user(self, aiohttp_client, app, setup_test_db):
        payload = {
            "name": "Test City",
            "latitude": 12.34,
            "longitude": 56.78,
            "user_id": 1
        }
        client = await aiohttp_client(app)
        resp = await client.post('/city', json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert "message" in data
        assert "Test City" in data["message"]

        async with aiosqlite.connect(setup_test_db) as db:
            cursor = await db.execute('SELECT name, latitude, longitude FROM cities WHERE name = ?', (payload["name"],))
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == payload["name"]
            assert row[1] == payload["latitude"]
            assert row[2] == payload["longitude"]
            cursor = await db.execute('SELECT city_id FROM user_city WHERE user_id = ?', (payload["user_id"],))
            assert row[0]

    async def test_add_city_without_name(self, aiohttp_client, app, setup_test_db):
        payload = {
            "latitude": 12.34,
            "longitude": 56.78
        }
        client = await aiohttp_client(app)
        resp = await client.post('/city', json=payload)
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data

    async def test_add_city_bad_chords(self, aiohttp_client, app, setup_test_db):
        payload = {
            "latitude": 1222.34,
            "longitude": 'abc',
            'name': 'Sample city'
        }
        client = await aiohttp_client(app)
        resp = await client.post('/city', json=payload)
        assert resp.status == 400
        data = await resp.json()
        assert "error" in data


class Test_city_list:

    async def test_get_city_list_no_user(self, aiohttp_client, app, setup_test_db):
        
        client = await aiohttp_client(app)
        resp = await client.get('/city')
        assert resp.status == 404
        payload = {
            "name": "Test City",
            "latitude": 12.34,
            "longitude": 56.78
        }
        resp = await client.post('/city', json=payload)
        assert resp.status == 200
        resp = await client.get('/city')
        assert resp.status == 200
        data = await resp.json()
        assert data[0]['name'] == payload['name']
        assert data[0]['latitude'] == payload['latitude']
        assert data[0]['longitude'] == payload['longitude']

    async def test_get_city_list_user(self, aiohttp_client, app, setup_test_db):
        
        client = await aiohttp_client(app)

        payload = {
            "name": "user_added",
            "latitude": 12.34,
            "longitude": 56.78,
            'user_id': 1
        }

        resp = await client.post('/city', json=payload)
        assert resp.status == 200

        resp = await client.get('/city?user_id=1')
        assert resp.status == 200
        data = await resp.json()
        assert data[0]['name'] == payload['name']
        
        payload2 = {
            "name": "globaly_added",
            "latitude": 13.34,
            "longitude": 51.78
        }

        resp = await client.post('/city', json=payload2)
        assert resp.status == 200

        resp = await client.get('/city?user_id=1')
        data = await resp.json()


        assert len(data) == 1

    async def test_get_city_list_no_cities(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        resp = await client.get('/city')
        assert resp.status == 404
        data = await resp.json()
        assert 'message' in data

class Test_city_weather:
    async def test_city_weather(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        payload = {
            "name": "Test City",
            "latitude": 12.34,
            "longitude": 56.78
        }
        await client.post('/city', json=payload)

        today = datetime.today()
        date = today.strftime(f"%Y-%m-%dT21:08")

        resp = await client.get(f'/city_weather?name=Test City&time={date}&params=temperature,wind_speed,precipitation')
        assert resp.status == 200
        data = await resp.json()
        assert all([par in data for par in ['temperature', 'wind_speed', 'precipitation']])


    async def test_city_weather_bad_date(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        payload = {
            "name": "Test City",
            "latitude": 12.34,
            "longitude": 56.78
        }
        await client.post('/city', json=payload)

        today = datetime.today()
        date = today.strftime(f"%Y-%m-%dT55:08")

        resp = await client.get(f'/city_weather?name=Test City&time={date}&params=temperature,wind_speed,precipitation')
        assert resp.status == 400
        data = await resp.json()
        assert 'error' in data

    async def test_city_weather_no_params(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        payload = {
            "name": "Test City",
            "latitude": 12.34,
            "longitude": 56.78
        }
        await client.post('/city', json=payload)

        today = datetime.today()
        date = today.strftime(f"%Y-%m-%dT14:08")

        resp = await client.get(f'/city_weather?name=Test City&time={date}')
        assert resp.status == 400
        data = await resp.json()
        assert 'error' in data

class Test_user:
    async def test_user(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        payload = {
            "name": "Andrew"
        }
        resp = await client.post('/user', json=payload)
        assert resp.status == 200
        data = await resp.json()
        assert 'user_id' in data

    async def test_user_no_name(self, aiohttp_client, app, setup_test_db):
        client = await aiohttp_client(app)
        payload = {}
        resp = await client.post('/user', json=payload)
        assert resp.status == 400
        data = await resp.json()
        assert 'error' in data