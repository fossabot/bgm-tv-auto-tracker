import asyncio
import pathlib
import json
from os import path
from typing import Callable

import motor.core
from validator import Validator, StringField, EnumField

import aiohttp_cors
import aiohttp
import aiohttp_jinja2
import jinja2
from aiohttp import web
from dateutil import parser

from config import APP_ID, APP_SECRET, HOST, PROTOCOL
from db import setup_mongo

callback_url = f'{PROTOCOL}://{HOST}/oauth_callback'
oauth_url = f'https://bgm.tv/oauth/authorize?client_id={APP_ID}&response_type=code&redirect_uri={callback_url}'

base_dir = pathlib.Path(path.dirname(__file__))


class TypeDatabase(object):
    bangumi: motor.core.AgnosticCollection
    token: motor.core.AgnosticCollection
    missing_bangumi: motor.core.AgnosticCollection
    get_collection: Callable[[str], motor.core.AgnosticCollection]


class TypeMongoClient(object):
    bilibili_bangumi: TypeDatabase
    pass


class TypeApp(web.Application):
    mongo: TypeMongoClient
    db: TypeDatabase


class WebRequest(web.Request):
    app: TypeApp


async def get_token(request: WebRequest, ):
    code = request.query.get('code', None)
    if not code:
        return aiohttp_jinja2.render_template('post_to_extension.html', request, {'data': json.dumps({
            "_id"          : 1,
            "access_token" : "example_access_token",
            "expires_in"   : 604800,
            "token_type"   : "Bearer",
            "scope"        : None,
            "user_id"      : 1,
            "refresh_token": "example_refresh_token",
            "auth_time"    : 1529418738
        }), })
    async with aiohttp.ClientSession() as session:
        async with session.post('https://bgm.tv/oauth/access_token',
                                data={'grant_type'   : 'authorization_code',
                                      'client_id'    : APP_ID,
                                      'client_secret': APP_SECRET,
                                      'code'         : code,
                                      'redirect_uri' : callback_url}) as resp:
            try:
                r = await resp.json()
            except aiohttp.client_exceptions.ContentTypeError:
                raise web.HTTPFound(oauth_url)
        if 'error' in r:
            return web.json_response(r, status=400)
        r['auth_time'] = int(parser.parse(resp.headers['Date']).timestamp())

        request.app.db.token.update_one({'_id': r['user_id']}, {'$set': r}, upsert=True)
        return aiohttp_jinja2.render_template('post_to_extension.html', request, {'data': json.dumps(r), })


async def refresh_auth_token(request: WebRequest, ):
    data = await request.json()
    refresh_token = data.get('refresh_token', None)
    user_id = data.get('user_id', None)
    if not (refresh_token and user_id):
        return web.HTTPBadRequest()
    data = {'grant_type'   : 'refresh_token',
            'client_id'    : APP_ID,
            'client_secret': APP_SECRET,
            'refresh_token': refresh_token,
            'redirect_uri' : callback_url}
    print(data)
    async with aiohttp.ClientSession() as session:
        async with session.post('https://bgm.tv/oauth/access_token', json=data) as resp:
            # async with session.post('https://postman-echo.com/post', json=data) as resp:
            r = await resp.json()
        print(r)
        if 'error' in r:
            return web.json_response(r)
        r['_id'] = r['user_id']
        r['auth_time'] = int(parser.parse(resp.headers['Date']).timestamp())

        request.app.db.token.update_one({'_id': r['_id']}, {'$set': r}, upsert=True)
        return web.json_response(r)


async def aio_get(url, headers=None):
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            return await resp.json()


async def aio_post(url, data=None, headers=None):
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(url, data=data) as resp:
            return await resp.json()


async def query_subject_id(request: WebRequest):
    website = request.query.get('website', None)
    bangumi_id = request.query.get('bangumiID', None)
    if not (website and bangumi_id and website in ['iqiyi', 'bilibili']):
        raise web.HTTPBadRequest(reason='missing input `website` or `bangumiID`')
    collection = request.app.db.get_collection(website)
    e = await collection.find_one({'_id': bangumi_id})
    if e:
        return web.json_response(e)
    else:
        raise web.HTTPNotFound()
    # request.mongo.get_data

    pass


class ReportMissingBangumiValidator(Validator):
    bangumiID = StringField(strict=False)
    subjectID = StringField()
    title = StringField()
    href = StringField()
    website = EnumField(choices=['bilibili', 'iqiyi'])


async def report_missing_bangumi(request: WebRequest):
    data = await request.json()
    v = ReportMissingBangumiValidator(data)
    if not v.is_valid():
        return web.json_response({'message': v.str_errors, 'code': 400, 'status': 'error'}, status=400)
    data = v.validated_data
    try:
        await request.app.db.missing_bangumi.insert_one(data)
        return web.json_response({'status': 'success'}, status=201)
    except Exception as e:
        return web.json_response({'status': 'error', 'message': str(e)}, status=502)


async def missing_bangumi(request: WebRequest):
    f = await request.app.db.missing_bangumi.find({}, {'_id': 0}).to_list(30)
    return web.json_response(f)


def redirect(location):
    async def r(*args):
        raise web.HTTPFound(location)

    return r


def create_app(io_loop=asyncio.get_event_loop()):
    app = web.Application(
        # middlewares=[error_middleware, ]
    )
    setup_mongo(app, io_loop)
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(str(base_dir / 'templates')))
    app.add_routes([
        web.get('/api/v0.1/missing_bangumi', missing_bangumi),
        web.post('/api/v0.1/refresh_token', refresh_auth_token),
        web.post('/api/v0.1/reportMissingBangumi', report_missing_bangumi),
        web.get('/', redirect('https://github.com/Trim21/bilibili-bangumi-tv-auto-tracker')),
        web.get('/oauth_callback', get_token),
        web.get('/api/v0.2/querySubjectID', query_subject_id),
    ])
    cors = aiohttp_cors.setup(app, defaults={
        "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    for route in list(app.router.routes()):
        cors.add(route)
    return app


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    web.run_app(create_app(io_loop=loop), port=6003)
