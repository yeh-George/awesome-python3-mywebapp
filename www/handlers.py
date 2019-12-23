# -*- coding: utf-8 -*-

'''
URL handlers
'''

import re, time, json, logging, hashlib, base64, asyncio

import markdown2

from aiohttp import web 

from coroweb import get, post
from apis import Page, APIValueError, APIResourceNotFoundError, APIError

from models import User, Comment, Blog, next_id
from config import configs


COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret

def check_admin(request):
    if request.__user__ is None or not request.__user__.admin:
        raise APIPermissionError()

def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p



def text2html(text):

    lines = map(lambda s: '<p>%s</p>' % s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'), filter(lambda s: s.strip() != '', text.split('\n')))

    return ''.join(lines)


def user2cookie(user, max_age):
    '''
    Generate cookie str by user.
    根据用户user.id得到一串验证字符串：user.id + 过期时间expires + sha1（用户ID，用户密码，过期时间，SecretKey）
    '''
    expires = str(int(time.time() + max_age))
    s = '%s-%s-%s-%s' % (user.id, user.passwd, expires, _COOKIE_KEY)
    L = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(L)
    
async def cookie2user(cookie_str):
    '''
    Parse cookie and load user if cookie is valid.
    '''
    if not cookie_str:
        #cookie_str不存在，不要
        return None
    try:
        L = cookie_str.split('-')
        if len(L) != 3:
        #cookie_str不是3个，不要
            return None
        uid, expires, sha1 = L
        if int(expires) < time.time():
        # 登录过期了，不要
            return None
        user = await User.find(uid)
        if user is None:
            #用户不存在，不要
            return None
        s = '%s-%s-%s-%s' % (uid, user.passwd, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            # sha1不对，不要
            # 为什么不是密码不对，不要呢？因为passwd不存在cookie_str中
            logging.info('invalid sha1')
            return None
        user.passwd = '******'
        #return之前就已经把用户passwd给屏蔽了
        return user
    except Except as e:
        logging.exception(e)
        return None


###后端API
_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')

#   获取用户： GET /api/users
@get('/api/users')
async def api_users_get(*, page='1'):
    page_index = get_page_index(page)
    num = await User.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, users=())
    users = await User.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    for u in users:
        u.passwd = '******'
    return dict(page=p, users=users)

#   创建用户： POST /api/users   
@post('/api/users')
async def api_user_register(*, email, name, passwd):
    #check
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not passwd or not _RE_SHA1.match(passwd):
        raise APIValueError('passwd')
    users = await User.findAll('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'Email has been registered.')

    #create
    uid = next_id()
    sha1_passwd = '%s:%s' % (uid, passwd)
    user = User(id=uid, name=name.strip(), email=email, passwd=hashlib.sha1(sha1_passwd.encode('utf-8')).hexdigest(), image='about:blank')
    await user.save()
    
    #make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=864000, httponly=True)
    user.passwd = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')   
    return r
    
#   获取日志：GET /api/blogs
@get('/api/blogs')
async def api_blogs_get(*, page='1'):
    page_index = get_page_index(page)
    item_count = await Blog.findNumber('count(id)')
    p = Page(item_count, page_index)

    if item_count == 0:
        return dict(page=p, blogs=())
        
    blogs = await Blog.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    
    return dict(page=p, blogs=blogs)

#   获取单条日志：GET /api/blogs/{id}
@get('/api/blogs/{id}')
async def api_blog_get(*, id):
    blog = await Blog.find(id)
    return blog
    
#   创建日志：POST /api/blogs
@post('/api/blogs')
async def api_blog_create(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'blog name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'blog summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'blog content cannot be empty.')
    blog = Blog(user_id=request.__user__.id, user_name=request.__user__.name, user_image=request.__user__.image, 
                    name=name.strip(), summary=summary.strip(), content=content.strip())
    await blog.save()
    return blog
  
#   修改日志：POST /api/blogs/blog_id
@post('/api/blogs/{id}')  
async def api_blog_update(id, request, *, name, summary, content):
    check_admin(request)
    blog = await Blog.find(id)
    if not name or not name.strip():
        raise APIValueError('name', 'blog name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'blog summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'blog content cannot be empty.')
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    await blog.update()
    return blog

#   删除日志：POST /api/blogs/blogs_id/delete
@post('/api/blogs/{id}/delete')
async def api_blog_delete(request, *, id):
    check_admin(request)
    blog = await Blog.find(id)
    await blog.remove()
    return dict(id=id)

#   获取评论：GET /api/comments
@get('/api/comments')
async def api_comments_get(*, page='1'):
    page_index = get_page_index(page)
    num = await Comment.findNumber('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, comments=())
    comments = await Comment.findAll(orderBy='created_at desc', limit=(p.offset, p.limit))
    return dict(page=p, comments=comments)
    
#   创建评论：POST /api/blogs/blog_id/comments
@post('/api/blogs/{id}/comments')
async def api_comment_create(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin.')
    if not content or not content.strip():
        raise APIValueError('content', 'comment content cannot be empty.')
    print('id %s' % id)
    blog = await Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(blog_id=blog.id, user_id=user.id, user_name=user.name, user_image=user.image,
                        content=content.strip())
    await comment.save()
    return comment

#   删除评论：POST /api/comments/comment_id/delete
@post('/api/comments/{id}/delete')
async def api_comment_delete(id, request):
    # check_admin验证user是不是管理者，只有管理者才有修改删除权限，普通用户，即使是comment的创建者也不能修改删除。
    check_admin(request)
    c = await Comment.find(id)
    if c is None:
        raise APIResourceNotFoundError('Comment')
    await c.remove()
    return dict(id=id)

###管理页面
@get('/manage')
def manage():
    return 'redirect:/manage/comments'
    
#   评论列表页： GET /manage/comments
@get('/manage/comments')
def manage_comments(*, page='1'):
    return {
        '__template__': 'manage_comments.html',
        'page_index': get_page_index(page)
    }
    
#   用户列表页： GET /manage/users
@get('/manage/users')
def manage_users(*, page='1'):
    return {
        '__template__': 'manage_users.html',
        'page_index': get_page_index(page)
    }

#   日志列表页： GET /manage/blogs
@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }
    
#       日志创建页： GET /manage/blogs/create
@get('/manage/blogs/create')
def manage_blog_create():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }
    
#       日志修改页： GET /manage/blogs/edit
@get('/manage/blogs/edit')
def manage_blog_edit(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/%s' % id
    }
        
        
### 用户浏览页面
#   首页（日志展示页）： GET /
@get('/')
async def index(*, page='1'):
    page_index = get_page_index(page)
    item_count = await Blog.findNumber('count(id)')
    page = Page(item_count, page_index)
    
    if item_count == 0:
        blogs = []
    else:
        blogs = await Blog.findAll(orderBy='created_at desc', limit=(page.offset, page.limit))
    return {
        '__template__': 'index.html',
        'page': page,
        'blogs': blogs
    }
    
#   日志详情页：GET /blog/blog_id
@get('/blog/{id}')
async def get_blog(id):
    blog = await Blog.find(id)
    comments = await Comment.findAll('blog_id=?', [id], orderBy='created_at desc')
    for c in comments:
        c.html_content = text2html(c.content)
    
    blog.html_content = markdown2.markdown(blog.content.replace('<script>', '&lt;script&gt;').replace('</script>', '&lt;/script&gt;').replace('"', '&quot;').replace('_', '&#95;'))
    
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }
    
#   注册页： GET /register
@get('/register')
def register():
    return {
        '__template__': 'register.html',
    }
    

#   登录页： GET /signin
@get('/signin')
def signin():
    return {
        '__template__': 'signin.html'
    }
    
@post('/api/authenticate')
async def authenticate(*, email, passwd):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not passwd:
        raise APIValueError('passwd', 'Invalid password.')
    users = await User.findAll('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    
    # check passwd: id + : + passwd
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(passwd.encode('utf-8'))
    if user.passwd != sha1.hexdigest():
        raise APIValueError('passwd', 'Invalid password.')
    
    # authenticate ok, set cookie.
    resp = web.Response()
    resp.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.passwd = '******'
    resp.content_type = 'application/json'
    resp.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    
    return resp
   
#   注销页： GET /signout
@get('/signout')
def signout(request):
    username = request.__user__.name
    print(username)
    referer = request.headers.get('Referer') #获得的是跳转前一个页面的url地址
    print(referer)
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user %s signed out.' % username)
    return r
    
    #signout 为什么不用r = web.Response(), r.set_cookie()?

    
    










    
    
    
    
    
    
    