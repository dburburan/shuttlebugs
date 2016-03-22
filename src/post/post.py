from google.appengine.ext import db

import cgi

from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

from django.template.defaultfilters import slugify

import re

import datetime
import pytz

from appengine_utilities import sessions
from sbuser import is_current_user_admin, create_login_url, get_current_user_name

#Models

class Post(db.Model):
    title = db.StringProperty()
    slug = db.StringProperty()
    type = db.StringProperty()
    content = db.TextProperty()
    author = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)
    hidden = db.BooleanProperty(default=False)
    active = db.BooleanProperty(default=True)

    @staticmethod
    def get_pages():
        pages = db.GqlQuery('''
            SELECT * FROM Post
            WHERE type = 'page'
            AND active = TRUE
            AND hidden = FALSE
            ORDER BY title         
            ''').fetch(1000)
        return [ page.title for page in pages ]

    # override put() to auto populate some fields
    def put(self,*args,**kw):
        self.author = sessions.Session()['user']
        self.slug = unicode(slugify(self.title))
        return db.Model.put(self,*args,**kw)
        

#Request Handlers

def convert_emails(text):
    return re.sub(
        r'(?<!mailto:)\b(\w+@[\w.]+)\b',
        r'<a href="mailto:\1">\1</a>',
        text)

class DisplayNews(webapp.RequestHandler):
    def get(self):        
        today = datetime.date.today()
        six_months = datetime.timedelta(180)
        
        news = db.Query(Post).filter('type =','news').filter('date >=',today-six_months).order('-date').fetch(100)
        au_tz = pytz.timezone('Australia/Sydney')
        utc_tz = pytz.utc
        for item in news:
            item.date = utc_tz.localize(item.date).astimezone(au_tz)
        data = {
            'page_title'    : 'Recent News',
            'posts'         : news,
            'session'       : sessions.Session(),
            'pages'         : Post.get_pages(),
        }
        return self.response.out.write(unicode(template.render('post/news.html',data)))

class DisplayPost(webapp.RequestHandler):
    
    def get(self,slug):
        try:
            post = db.GqlQuery('''
                SELECT * FROM Post
                WHERE slug = '%s'
                AND type = 'page'
                AND active = TRUE
                LIMIT 1
                ''' % slug)[0]
        except IndexError:
            self.error(404)
            data = {
                'pages'     : Post.get_pages(),
                'session'   : sessions.Session(),
            }
            return self.response.out.write(unicode(template.render('404.html',data)))
        data = {
            'page_title'    : post.title,
            'content'       : convert_emails(post.content),
            'pages'         : Post.get_pages(),
            'session'       : sessions.Session(),
        }
        return self.response.out.write(unicode(template.render('post/page.html',data)))    

class DeleteNews(webapp.RequestHandler):
    def get(self,key):
        user = get_current_user_name()
        if not user:
            return self.redirect(create_login_url(self.request.uri))
        if not is_current_user_admin():
            sessions.Session()['flash'] = ['You must be an admin to delete pages.']
            return self.redirect('/')
           
        # delete the post
        Post.get(db.Key(key)).delete()
        
        sessions.Session()['flash'] = ['News item deleted succesfully.']
        return self.redirect('/news')

class DeletePost(webapp.RequestHandler):
    def get(self,slug):
        user = get_current_user_name()
        if not user:
            return self.redirect(create_login_url(self.request.uri))
        if not is_current_user_admin():
            sessions.Session()['flash'] = ['You must be an admin to delete pages.']
            return self.redirect('/')
           
        # get the existing post
        post = db.GqlQuery('''
            SELECT * FROM Post
            WHERE slug = '%s'
            AND type = 'page'
            LIMIT 1
            ''' % slug)[0]
            
        post.active = False
        post.put()
        sessions.Session()['flash'] = ['Page deleted succesfully.']
        return self.redirect('/')

class EditNews(webapp.RequestHandler):
    
    def get(self,key):
        user = get_current_user_name()
        if not user:
            return self.redirect(create_login_url(self.request.uri))
           
        # get the existing post
        post = Post.get(key)
        
        data = {
            'session'   : sessions.Session(),
            'pages'     : Post.get_pages(),
            'title'     : post.title,
            'type'      : post.type,
            'key'       : key,
            'content'   : post.content,
        }
        return self.response.out.write(unicode(template.render('post/edit.html',data)))
        
    def post(self,key):
        user = get_current_user_name()
        
        title = self.request.get('title')
        content = self.request.get('content')

        # get the existing post
        post = Post.get(key)

        errors = []
        if not is_current_user_admin():
            errors.append('Only admins can edit')
        if not user:
            errors.append('You need to be logged in to edit')
        if not title or not content:
            errors.append('Please fill out all fields') 
        if errors:
            session = sessions.Session()
            session['flash'] = errors
            data = {
                'title'     : title,
                'content'   : content,
                'session'   : session,
                'type'      : post.type,
                'key'       : key,
                'pages'     : Post.get_pages(),
                }
            return self.response.out.write(unicode(template.render('post/edit.html',data)))

        post.title = title
        post.content = content
        post.put()
        
        return self.redirect('/news')

class EditPost(webapp.RequestHandler):
    
    def get(self,slug):
        user = get_current_user_name()
        if not user:
            return self.redirect(create_login_url(self.request.uri))
           
        # get the existing post
        post = db.GqlQuery('''
            SELECT * FROM Post
            WHERE slug = '%s'
            AND type = 'page'
            LIMIT 1
            ''' % (slug))[0]
            
        data = {
            'session'   : sessions.Session(),
            'pages'     : Post.get_pages(),
            'title'     : post.title,
            'type'      : post.type,
            'content'   : post.content,
        }
        return self.response.out.write(unicode(template.render('post/edit.html',data)))
        
    def post(self,slug):
        user = get_current_user_name()
        
        title = self.request.get('title')
        content = self.request.get('content')

        # get the existing post
        post = db.GqlQuery('''
            SELECT * FROM Post
            WHERE slug = '%s'
            AND type = 'page'
            LIMIT 1
            ''' % slug)[0]

        # if it's a page, and you've changed the title
        # check that the new title/slug has not already been used
        existing = False
        if post.type == 'page' and title != post.title:
            existing = Post.all().filter('type =', 'page').filter('slug =', unicode(slugify(title))).fetch(1)

        errors = []
        if not is_current_user_admin():
            errors.append('Only admins can edit')
        if not user:
            errors.append('You need to be logged in to edit')
        if not title or not content:
            errors.append('Please fill out all fields')
        if existing:
            errors.append('A page with this title already exists')            
        if errors:
            session = sessions.Session()
            session['flash'] = errors
            data = {
                'title'     : title,
                'content'   : content,
                'session'   : session,
                'type'      : post.type,
                'pages'     : Post.get_pages(),
                }
            return self.response.out.write(unicode(template.render('post/edit.html',data)))

        post.title = title
        post.content = content
        post.put()

        return self.redirect('/page/%s' % unicode(slugify(title)))
    
class CreatePost(webapp.RequestHandler):
    
    def get(self):
        sess = sessions.Session()
        if not sess.has_key('user') or not sess['user']:
            return self.redirect(create_login_url(self.request.uri))            
        data = {
            'session' : sess,
            'pages'   : Post.get_pages(),
        }
        return self.response.out.write(unicode(template.render('post/post.html',data)))
        
    def post(self):        
        title = self.request.get('title')
        type = self.request.get('type')
        content = self.request.get('content')
        
        
        # if it's a page, check that the title/slug has not already been used
        existing = False
        if type == 'page':
            existing = Post.all().filter('type =', 'page').filter('slug =', unicode(slugify(title))).fetch(1)

        errors = []
        if not is_current_user_admin():
            errors.append('Only admins can post')
        if not get_current_user_name():
            errors.append('You need to be logged in to post')
        if not title or not type or not content:
            errors.append('Please fill out all fields')
        if existing:
            errors.append('A page with this title already exists')
        if type not in ['news','announcement','page','pdf']:
            errors.append('Invalid page type')            
        if errors:
            session = sessions.Session()
            session['flash'] = errors
            data = {
                'title'     : title,
                'type'      : type,
                'content'   : content,
                'session'   : session,
                'pages'     : Post.get_pages(),
                }
            return self.response.out.write(unicode(template.render('post/post.html',data)))

        fixed_type = type
        if fixed_type == 'pdf':
            fixed_type = 'page'

        new_post = Post(
            title = title,
            type = fixed_type,
            content = content
        )
        if fixed_type == 'page':
            new_post.hidden = True
        new_post.put()
        
        if fixed_type == 'page':
            return self.redirect('/%s.html' % new_post.slug)
        else:
            return self.redirect('/')
        
class ManagePages(webapp.RequestHandler):
    
    def __compose(self,messages=[]):        
        active_pages = Post.all().filter('type =','page').filter('active =',True).filter('hidden =',False).order('-date').fetch(1000)
        hidden_pages = Post.all().filter('type =','page').filter('active =',True).filter('hidden =',True).order('-date').fetch(1000)
        deleted_pages = Post.all().filter('type =','page').filter('active =',False).order('-date').fetch(1000)
        
        data = {
            'messages'  : messages,
            'session'   : sessions.Session(),
            'active'    : active_pages,
            'hidden'    : hidden_pages,
            'deleted'   : deleted_pages,
            'pages'     : Post.get_pages(),
        }
        
        return self.response.out.write(unicode(template.render('post/manage.html',data)))
    
    def get(self):      
        return self.__compose()
        
    def post(self):
        user = get_current_user_name()
        if not user:
            return self.redirect(create_login_url(self.request.uri))

        slug = self.request.get('slug')
        action = self.request.get('action')

        messages = []
        if not is_current_user_admin():
            messages.append('Only admins can manage pages')
        if not user:
            messages.append('You need to be logged in to manage pages')
        if not slug:
            messages.append('Please specify which page you would like to change')
        if not action:
            messages.append('Please specify what you would like to do')
        if messages:
            return self.__compose(messages)
            
        # get the existing post
        post = db.GqlQuery('''
            SELECT * FROM Post
            WHERE slug = '%s'
            AND type = 'page'
            LIMIT 1
            ''' % slug)[0]
        if action == 'delete':  
            post.active = False
            messages.append('%s deleted' % slug)
        elif action == 'undelete':
            post.active = True
            messages.append('%s undeleted' % slug)
        elif action == 'hide':
            post.hidden = True
            messages.append('%s hidden' % slug)
        elif action == 'unhide':
            post.hidden = False
            messages.append('%s unhidden' % slug)
        elif action == 'edit':
            return self.redirect('/page/edit/%s' % slug)
        # save the changes
        post.put()
            
        return self.redirect(self.request.uri)        
        
        
            
        
