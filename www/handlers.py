import re, time, json, logging, hashlib, base64, asyncio

from aiohttp import web 

from coroweb import get, post

@get('/')
def index(request):
    return b'hello'