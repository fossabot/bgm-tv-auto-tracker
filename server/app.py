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

github_url = 'https://github.com/Trim21/bilibili-bangumi-tv-auto-tracker'
callback_url = f'{PROTOCOL}://{HOST}/oauth_callback'
oauth_url = f'https://bgm.tv/oauth/authorize?client_id={APP_ID}' \
            f'&response_type=code&redirect_uri={callback_url}'

base_dir = pathlib.Path(path.dirname(__file__))


class TypeDatabase(object):
    bangumi: motor.core.AgnosticCollection
    token: motor.core.AgnosticCollection
    missing_bangumi: motor.core.AgnosticCollection
    get_collection: Callable[[str], motor.core.AgnosticCollection]
    statistics_missing_bangumi: motor.core.AgnosticCollection


class TypeMongoClient(object):
    bilibili_bangumi: TypeDatabase
    pass


class TypeApp(web.Application):
    db: TypeDatabase
    mongo: TypeMongoClient
    client_session: aiohttp.ClientSession


class WebRequest(web.Request):
    app: TypeApp


async def get_token(request: WebRequest, ):
    code = request.query.get('code', None)

    if not code:
        raise web.HTTPFound(location=oauth_url)

    async with request.app.client_session.post(
        'https://bgm.tv/oauth/access_token',
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
    await request.app.db.token.find_one({'_id': r['user_id']})
    await request.app.db.token.update_one({'_id': r['user_id']},
                                          {'$set': r},
                                          upsert=True)
    return aiohttp_jinja2.render_template('post_to_extension.html', request,
                                          {'data': json.dumps(r), })


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
    async with request.app.client_session \
        .post('https://bgm.tv/oauth/access_token', json=data) as resp:
        try:
            r = await resp.json()
        except aiohttp.client_exceptions.ContentTypeError:
            return web.json_response({}, status=504)
    if 'error' in r:
        return web.json_response(r)
    r['_id'] = r['user_id']
    r['auth_time'] = int(parser.parse(resp.headers['Date']).timestamp())
    await request.app.db.token.update_one({'_id': r['_id']}, {'$set': r},
                                          upsert=True)
    return web.json_response(r)


async def query_subject_id(request: WebRequest):
    website = request.query.get('website', None)
    bangumi_id = request.query.get('bangumiID', None)
    if not (website and bangumi_id and website in ['iqiyi', 'bilibili']):
        raise web.HTTPBadRequest(
            reason='missing input `website` or `bangumiID`'
        )
    collection = request.app.db.get_collection(website)
    e = await collection.find_one({'_id': bangumi_id})
    if e:
        await request.app.db.statistics_missing_bangumi.delete_one(
            {'website': website, 'bangumi_id': bangumi_id},
        )
        return web.json_response(e)
    else:
        await request.app.db.statistics_missing_bangumi.update_one(
            {'website': website, 'bangumi_id': bangumi_id},
            {'$inc': {'times': 1}},
            upsert=True
        )
        raise web.HTTPNotFound()


class ReportMissingBangumiValidator(Validator):
    bangumiID = StringField(strict=False, required=True)
    subjectID = StringField(required=True)
    title = StringField(required=True)
    href = StringField(required=True)
    website = EnumField(choices=['bilibili', 'iqiyi'], required=True)


async def report_missing_bangumi(request: WebRequest):
    data = await request.json()
    v = ReportMissingBangumiValidator(data)

    if not v.is_valid():
        return web.json_response(
            {'message': v.str_errors,
             'code'   : 400,
             'status' : 'error'},
            status=400
        )
    data = v.validated_data
    try:
        await request.app.db.statistics_missing_bangumi.update_one(
            {'bangumi_id': data['bangumiID'], 'website': data['website']},
            {'$set': {'subject_id': data['subjectID'],
                      'title'     : data['title'],
                      'href'      : data['href']}},
        )
        return web.json_response({'status': 'success'})
    except Exception as e:
        return web.json_response({'status' : 'error',
                                  'message': str(e)},
                                 status=502)


website_template = {
    'bilibili': 'https://bangumi.bilibili.com/anime/{}',
    'iqiyi'   : 'https://www.iqiyi.com/{}.html'
}


async def statistics_missing_bangumi(request: WebRequest):
    subject = request.query.get('subject_id')
    condition = {}
    if subject == 'true':
        condition['subject_id'] = {'$exists': True}
    elif subject == 'false':
        condition['subject_id'] = {'$exists': False}
    f = await request.app.db.statistics_missing_bangumi \
        .find(condition, {'_id': 0}) \
        .sort([('times', -1), ('subject_id', 1)]).to_list(500)

    for item in f:
        item['bangumi_url'] = website_template \
            .get(item['website'], '{}').format(item['bangumi_id'])
        if item.get('subject_id'):
            item['subject_url'] = 'https://bgm.tv/subject/{}' \
                .format(item['subject_id'])
    return web.json_response(f)


def redirect(location):
    async def r(*args):
        raise web.HTTPFound(location)

    return r


import aiohttp.http


async def clean_up(app):
    await app.client_session.close()


def create_app(io_loop=asyncio.get_event_loop()):
    app = web.Application(
        # middlewares=[error_middleware, ]
    )

    app.on_cleanup.append(clean_up)
    app.client_session = aiohttp.ClientSession(loop=io_loop)
    setup_mongo(app, io_loop)
    aiohttp_jinja2.setup(app,
                         loader=jinja2.FileSystemLoader(
                             str(base_dir / 'templates')
                         ))
    app.add_routes([
        web.get('/', redirect(github_url)),
        web.get('/auth', redirect(oauth_url)),
        web.get('/oauth_callback', get_token),
        web.get('/api/v0.2/querySubjectID', query_subject_id),
        web.get('/statistics_missing_bangumi', statistics_missing_bangumi),
        web.post('/api/v0.1/refresh_token', refresh_auth_token),
        web.post('/api/v0.1/reportMissingBangumi', report_missing_bangumi),
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
