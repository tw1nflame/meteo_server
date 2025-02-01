import asyncio
from datetime import datetime
from aiohttp import ClientSession, web
import aiosqlite


routes = web.RouteTableDef()
API_URL = f'https://api.open-meteo.com/v1/forecast'
DATABASE = 'weather.db'


async def clean_db(app):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('DROP TABLE IF EXISTS cities;')
        await db.execute('DROP TABLE IF EXISTS forecasts;')
        await db.execute('DROP TABLE IF EXISTS users;')
        await db.execute('DROP TABLE IF EXISTS user_city;')
        await db.commit()


async def init_db(app):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS cities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS forecasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_id INTEGER NOT NULL,
                forecast_time TEXT NOT NULL,
                temperature REAL,
                wind_speed REAL,
                precipitation REAL,
                humidity REAL,
                FOREIGN KEY (city_id) REFERENCES cities (id)
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS user_city (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                city_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY (city_id) REFERENCES cities (id),
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
    
        await db.commit()


@routes.get('/weather')
async def fetch_weather(request):

    latitude = request.query.get('latitude')
    longitude = request.query.get('longitude')

    try:
        latitude, longitude = validate_coordinates(latitude, longitude)
    except ValueError as e:
        return web.json_response({'error': str(e)}, status=400)


    params = {
        'latitude': latitude,
        'longitude': longitude,
        'current': 'temperature_2m,pressure_msl,wind_speed_10m'
    }

    async with ClientSession() as session:
        async with session.get(API_URL, params=params) as resp:
            weather_data = await resp.json()
            
    current_weather = weather_data['current']

    response = {
        'temperature': current_weather.get('temperature_2m'),
        'wind_speed': current_weather.get('wind_speed_10m'),
        'pressure': current_weather.get('pressure_msl')
    }

    return web.json_response(response)


@routes.post('/city')
async def add_city(request):

    data = await request.json()


    name = data.get('name')
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    try:
        latitude, longitude = validate_coordinates(latitude, longitude)
    except ValueError as e:
        return web.json_response({'error': str(e)}, status=400)
    
    if not name:
        return web.json_response({'error': 'Name is required'}, status=400)




    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute(
        'INSERT INTO cities (name, latitude, longitude) VALUES (?, ?, ?)',
        (name, latitude, longitude),
        )
        city_id = cursor.lastrowid

        
        if 'user_id' in data:
            await db.execute('INSERT INTO user_city (city_id, user_id) VALUES (?, ?)', (city_id, data['user_id']))

        await db.commit()

    await insert_city_weather(city_id, latitude, longitude)



    return web.json_response({'message': f'City {name} added successfully',
                              'id': city_id})


@routes.get('/city')
async def city_list(request):
    user_id = request.query.get('user_id', '')
    user_filter = ''
    
    query_params = ()

    if user_id:
        user_filter = f' WHERE id IN (SELECT city_id FROM user_city WHERE user_id = ?)'
        query_params += (user_id, )

    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute('SELECT name, latitude, longitude FROM cities' + user_filter, query_params) as cursor:
            cities = await cursor.fetchall()
    
    if not cities:
        return web.json_response({'message': 'No cities found'}, status=404)

    return web.json_response([{'name': name, 'latitude': latitude, 'longitude': longitude} for name, latitude, longitude in cities])


@routes.get('/city_weather')
async def city_weather(request):
    
    name = request.query.get('name')
    time = request.query.get('time')
    params = request.query.get('params', '').split(',')
    user_id = request.query.get('user_id', '')
    
    query_params = (name,)
    try:
        minutes = int(time[-2:])
        rounded_minutes = (minutes // 15) * 15
        time_to_search = f'{time[:-2]}{rounded_minutes:02d}'
        datetime.strptime(time_to_search, "%Y-%m-%dT%H:%M")
    except:
        return web.json_response({'error': 'Invalid date provided'}, status=400)


    user_filter = ''

    if user_id:
        user_filter = f' AND id IN (SELECT city_id FROM user_city WHERE user_id = ?)'
        query_params += (user_id,)

    
    valid_fields = {'temperature', 'wind_speed', 'humidity', 'precipitation'}
    fields_to_fetch = [field for field in params if field in valid_fields]

    if not fields_to_fetch:
        return web.json_response({'error': 'Invalid parameters provided'}, status=400)

    if not name:
        return web.json_response({'error': 'Name is required'}, status=400)

    
    async with aiosqlite.connect(DATABASE) as db:
        async with db.execute('SELECT id FROM cities WHERE name = ?' + user_filter, query_params) as cursor:
            city_row = await cursor.fetchone()
            if city_row is None:
                return web.json_response({'error': 'City not found'}, status=404)
            city_id, = city_row

        query = f'SELECT {', '.join(fields_to_fetch)} FROM forecasts WHERE city_id = ? AND forecast_time = ?'
        
        async with db.execute(query, (city_id, time_to_search)) as cursor:
            result = await cursor.fetchone()

    response = dict(zip(fields_to_fetch, result))
    
    return web.json_response(response)


@routes.post('/user')
async def get_user_id(request):

    data = await request.json()
    name = data.get('name')

    if not name:
        return web.json_response({'error': 'Name is required'}, status=400)


    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('INSERT INTO users (name) VALUES (?)', (name,))
        user_id = cursor.lastrowid
        await db.commit()

    return web.json_response({'user_id': user_id})


async def get_forecast_lists(latitude, longitude):

    params = {
        'latitude': latitude,
        'longitude': longitude,
        'minutely_15': 'temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m',
        'forecast_days': 1
    }


    async with ClientSession() as session:
        async with session.get(API_URL, params=params) as resp:
            weather_data = await resp.json()

    minutely_data = weather_data['minutely_15']
    time_list = minutely_data['time']
    temp_list = minutely_data['temperature_2m']
    humidity_list = minutely_data['relative_humidity_2m']
    precipitation_list = minutely_data['precipitation']
    wind_speed_list = minutely_data['wind_speed_10m']

    return time_list, temp_list, humidity_list, precipitation_list, wind_speed_list


async def update_city_weather(city_id, latitude, longitude):

    print(f'{city_id} forecast updated')

    time_list, temp_list, humidity_list, precipitation_list, wind_speed_list = await get_forecast_lists(latitude, longitude)
    
    async with aiosqlite.connect(DATABASE) as db:

        await db.executemany(
            'UPDATE forecasts SET temperature = ?, wind_speed = ?, humidity = ?, precipitation = ? WHERE city_id = ? AND forecast_time = ?;',
            [(temp, wind_speed, humidity, precipitation, city_id, time)
            for time, temp, humidity, precipitation, wind_speed in zip(time_list, temp_list, humidity_list, precipitation_list, wind_speed_list)]
        )
        await db.commit()


async def insert_city_weather(city_id, latitude, longitude):
    time_list, temp_list, humidity_list, precipitation_list, wind_speed_list = await get_forecast_lists(latitude, longitude)

    async with aiosqlite.connect(DATABASE) as db:
        await db.executemany(
            'INSERT INTO forecasts (city_id, forecast_time, temperature, wind_speed, humidity, precipitation) VALUES (?, ?, ?, ?, ?, ?)',
            [(city_id, time, temp, wind_speed, humidity, precipitation)
             for time, temp, humidity, precipitation, wind_speed in zip(time_list, temp_list, humidity_list, precipitation_list, wind_speed_list)]
        )
        await db.commit()


async def periodic_weather_update(app):
    
    while True:
        async with aiosqlite.connect(DATABASE) as db:
            async with db.execute('SELECT id, latitude, longitude FROM cities') as cursor:
                async for city_id, latitude, longitude in cursor:
                    await update_city_weather(city_id, latitude, longitude)

        await asyncio.sleep(15 * 60)


def validate_coordinates(latitude: str, longitude: str):
    try:
        latitude = float(latitude)
        longitude = float(longitude)
        if not (-90 <= latitude <= 90):
            raise ValueError('Latitude must be between -90 and 90')
        if not (-180 <= longitude <= 180):
            raise ValueError('Longitude must be between -180 and 180')
        return latitude, longitude 
    except (ValueError, TypeError) as e:
        raise ValueError(f'Invalid latitude or longitude: {str(e)}')


async def start_periodic_weather_update(app):
    app['weather_update_task'] = asyncio.create_task(periodic_weather_update(app))


async def cleanup_periodic_weather_update(app):
    weather_task = app.get('weather_update_task')
    if weather_task:  
        weather_task.cancel()  
        try:
            await weather_task 
        except asyncio.CancelledError:
            pass 


app = web.Application()
app.add_routes(routes)

app.on_startup.append(init_db)
app.on_startup.append(start_periodic_weather_update)
app.on_cleanup.append(cleanup_periodic_weather_update)


if __name__ == '__main__':
    web.run_app(app, port=8000)
