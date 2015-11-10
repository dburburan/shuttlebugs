from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from datetime import date

from google.appengine.ext.db import djangoforms

from sbuser import create_login_details, get_current_user_name, is_current_user_admin, create_login_url, get_email
from appengine_utilities import sessions as util_sess
from post import Post

from time import strptime
import datetime
from django.template.defaultfilters import slugify

from django.utils import simplejson
from google.appengine.api import urlfetch
from urllib import quote

# Models
class Session(db.Model):
    name = db.StringProperty(required=True)
    slug = db.StringProperty()
    day_of_week = db.StringProperty(
        required=True,
        choices=[
            'Monday',
            'Tuesday',
            'Wednesday',
            'Thursday',
            'Friday',
            'Saturday',
            'Sunday'
            ]
        )
    ordering = db.IntegerProperty()
    start_time = db.TimeProperty(required=True)
    end_time = db.TimeProperty(required=True)
    location = db.StringProperty(multiline=True)
    leader = db.StringProperty()
    courts = db.IntegerProperty()
    member_price = db.FloatProperty()
    casual_price = db.FloatProperty()
    description = db.TextProperty()
    coordinates = db.GeoPtProperty()
    active = db.BooleanProperty(default=False)
    def update_coordinates(self):
        try:
            url = 'http://maps.google.com/maps/api/geocode/json?address=%s&sensor=false' % quote(self.location)
            result = urlfetch.fetch(url)
        except urlfetch.DownloadError:
            self.coodinates = None
            return
        if result.status_code == 200:
            data = simplejson.loads(result.content)
        else:
            self.coodinates = None
            return
        if data['status'] != 'OK':
            self.coodinates = None
            return
        try:
            coords = data['results'][0]['geometry']['location']
            print coords
        except KeyError, IndexError:
            self.coodinates = None
            return
        self.coordinates = '%s,%s' % (coords['lat'],coords['lng'])
    # override put() to auto populate some fields    
    def put(self,*args,**kw):
        self.slug = slugify(self.name)
        existing = db.Query(Session).filter('slug =',self.slug).get()
        if existing and existing.key() != self.key():
            raise db.Error('A session already exists with a similar name: "%s".' % existing.name)
        days = {
            'Monday'    : 1,
            'Tuesday'   : 2,
            'Wednesday' : 3,
            'Thursday'  : 4,
            'Friday'    : 5,
            'Saturday'  : 6,
            'Sunday'    : 7,
        }
        self.ordering = days[self.day_of_week]
        self.update_coordinates()
        return db.Model.put(self,*args,**kw)    
    
class Cancellation(db.Model):
    date = db.DateProperty(required=True)
    reason = db.StringProperty(required=True)
    author = db.StringProperty(required=True)
    created = db.DateProperty(auto_now_add=True, required=True)

class SessionNotice(db.Model):
    date = db.DateProperty(required=True)
    reason = db.StringProperty(required=True)
    author = db.StringProperty(required=True)
    created = db.DateProperty(auto_now_add=True, required=True)
    type = db.StringProperty(required=True)


# Forms
class SessionForm(djangoforms.ModelForm):
    class Meta:
        model = Session
        exclude = ['ordering','slug','coordinates']

# Helpers
def login_required(funct):
    def new_funct(self,*args,**kw):
        user = get_current_user_name()
        if not user:
            util_sess.Session()['flash'] = ['You must login to use this feature.']
            return self.redirect(create_login_url(self.request.uri))
        return funct(self,*args,**kw)
    return new_funct

# Handler

class DisplaySessions(webapp.RequestHandler):
    def get(self):
        db_sessions = db.Query(Session).filter('active =',True).order('ordering').fetch(100)
        sessions = []
        for s in db_sessions:
            cur = {
                'name'          : s.name,
                'day_of_week'   : s.day_of_week,
                'start_time'    : s.start_time,
                'end_time'      : s.end_time,
                'location'      : s.location,
                'quoted_loc'    : quote(s.location),
                'description'   : s.description,
                'member_price'  : s.member_price,
                'casual_price'  : s.casual_price,
                'courts'        : s.courts,
                'leader'        : s.leader,
                'coords'        : s.coordinates,
            }
            if s.leader:
                leader_name = s.leader.strip().split(' ')
                cur['email'] = get_email(*leader_name[0:2])
            else:
                cur['email'] = 'holy moly'
            sessions.append(cur)
                
        data = {
            'pages'         : Post.get_pages(),
            'session'       : util_sess.Session(),
            'sessions'      : sessions,
        }
        return self.response.out.write(unicode(template.render('session/sessions.html',data)))

class EditSession(webapp.RequestHandler):
    
    def __compose(self,name,form,web_sess):
        data = {
            'pages'         : Post.get_pages(),
            'session'       : web_sess,
            'session_form'  : form,
            'sess_name'     : name,
        }
        return self.response.out.write(unicode(template.render('session/edit.html',data)))        
    
    @login_required
    def get(self,session_slug):
        session = db.Query(Session).filter('slug =',session_slug).get()
        sess = util_sess.Session()
        if not session:
            sess['flash'] = ['Session does not exist.']
            self.error(404)
            data = {
                'pages'     : Post.get_pages(),
                'session'   : sess,
            }            
            return self.response.out.write(unicode(template.render('404.html',data)))
        
        session_form = SessionForm(instance=session)
        
        return self.__compose(session.name,session_form,sess)

    @login_required
    def post(self,session_slug):
        session = db.Query(Session).filter('slug =',session_slug).get()
        sess = util_sess.Session()
        
        if not session:
            sess['flash'] = ['Session does not exist.']
            self.error(404)
            data = {
                'pages'     : Post.get_pages(),
                'session'   : sess,
            }            
            return self.response.out.write(unicode(template.render('404.html',data)))        
               
        try:
            input_data = SessionForm(instance=session,data=self.request.POST)
            if input_data.is_valid():
                input_data.save()
                sess['flash'] = ['Session succesfully saved.']
                return self.redirect('/session')
                return self.redirect('/session/edit/%s'%session.slug)
            else:
                sess['flash'] = ['There were errors in your form, see below.']
        except db.Error, e:
            sess['flash'] = ['Error saving session: %s' % e]
            
        return self.__compose(session.name,input_data,sess)


class ManageSession(webapp.RequestHandler):
    # view current session information
    
    def __compose(self,messages=[],notice_data=None,session_data=None):
        sessionnotices = db.Query(SessionNotice).filter('date >=',datetime.date.today()).order('-date').fetch(100)
        sessions = db.Query(Session).order('ordering').fetch(100)
        
        if session_data:
            session_form = session_data
        else:
            session_form = SessionForm()
        
        data = {
            'messages'      : messages,
            'next'          : next_session_widget(10),
            'sessions'      : sessions,
            'sessionnotices': sessionnotices,
            'session_form'  : session_form,
            'pages'         : Post.get_pages(),
            'session'       : util_sess.Session(),
            'notice_data'   : notice_data,
        }
        return self.response.out.write(unicode(template.render('session/manage.html',data)))    
    
    @login_required
    def get(self):
        return self.__compose()
    
    # cancel a session, add session or remove session
    @login_required
    def post(self):
        user = get_current_user_name()
        type = self.request.get('type')
        action = self.request.get('action')

        if type == 'sessionnotice':
            if action == 'add':
                try:
                    date_string = self.request.get('date')
                    date_input = datetime.date(*strptime(date_string,'%d/%m/%Y')[:3])
                    SessionNotice(
                        date = date_input,
                        reason = self.request.get('reason'),
                        type = self.request.get('noticetype'),
                        author = user,
                    ).put()
                except (db.Error,ValueError), e:
                    messages = ['Error saving note: %s'%e]
                    cancel_data = {
                        'date'      : date_input,
                        'reason'    : self.request.get('reason'),
                        'type'      : self.request.get('noticetype'),
                        }
                    return self.__compose(messages,notice_data=notice_data)
            elif action == 'del':
                try:
                    key = db.Key(self.request.get('key'))
                    db.get(key).delete()
                except (db.Error,ValueError,AttributeError), e:
                    messages = ['Error removing note: %s'%e]
                    return self.__compose(messages)    
        elif type == 'session':
            if action == 'add':
                try:
                    input_data = SessionForm(data=self.request.POST)
                    if input_data.is_valid():
                        input_data.save()
                    else:
                        return self.__compose(['There were errors in your form, see below.'], session_data=input_data)
                except db.Error, e:
                    return self.__compose(['Error saving session: %s' % e], session_data=input_data)

        return self.redirect(self.request.uri)

# Other Functions
def next_session_widget(days=7,vertical=False):
    ''' gets the next week's sessions and cancellations '''
    
    today = date.today()
    day = datetime.timedelta(days=1)
    
    sessions = db.Query(Session).filter('active =',True).order('ordering').fetch(100)
    
    ds_map = {}
    for session in sessions:
        try:
            ds_map[session.day_of_week].append(session)
        except KeyError:
            ds_map[session.day_of_week] = [session]
    out_dates = []
    out_sessions = []
    out_notices = []
    
    items = []
    
    for i in range(days):
        current = today + i * day
        
        try:
            todays_sessions = ds_map[current.strftime('%A')]
        except KeyError:
            todays_sessions = []
        
        items.append({
            'date'      : current,
            'sessions'  : todays_sessions,
            'notice'    : db.Query(SessionNotice).filter('date =',current).get(),
            })       
    
    data = {
        'dates'     : out_dates,
        'sessions'  : out_sessions,
        'notices'   : out_notices,
        'items'     : items,
        }
    
    if vertical:
        return template.render('session/nextvert.html',data)
    return template.render('session/next.html',data)

