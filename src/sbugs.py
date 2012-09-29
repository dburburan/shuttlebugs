from google.appengine.ext import webapp
from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext.webapp import template
from post import Post
from sbuser import create_login_details, get_username_mapping
from session import next_session_widget
from photos import pic_of_day_widget
from appengine_utilities import sessions

import datetime
import pytz

class SimplePost:
    def __init__(self,key,title,author,date,content):
        self.key = key
        self.title = title
        self.author = author
        self.date = date
        self.content = content

# Request Handlers

class Login(webapp.RequestHandler):
    def get(self):
        return self.redirect(users.create_login_url('/'))

class FrontPage(webapp.RequestHandler):
    
    def get(self):
        db_posts = db.GqlQuery('''
            SELECT * FROM Post
            WHERE type IN ('announcement', 'news')
            AND active = TRUE
            ORDER BY date
            DESC LIMIT 5                
            ''')
        posts = []
        au_tz = pytz.timezone('Australia/Sydney')
        utc_tz = pytz.utc
        for db_post in db_posts:
            post = SimplePost(
                db_post.key,
                db_post.title,
                db_post.author,
                utc_tz.localize(db_post.date).astimezone(au_tz),
                db_post.content)
            posts.append(post)        
        data = {
            'upcoming'      : next_session_widget(6),
            'picofday'      : pic_of_day_widget(),
            'posts'         : posts,
            'session'       : sessions.Session(),
            'pages'         : Post.get_pages(),
        }
        return self.response.out.write(template.render('index.html',data))    

