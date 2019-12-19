import re, time, json, logging, hashlib, base64, asyncio

from aiohttp import web 

from coroweb import get, post
from models import User, Blog, Comment

@get('/')
async def index(request):
    users = await User.findAll()
    return {
        '__template__': 'test.html',
        'users': users
    }