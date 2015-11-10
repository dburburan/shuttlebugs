from google.appengine.ext import db
from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.api import mail

from hashlib import md5
from appengine_utilities import sessions

import random

import post

# Models
class SBUser(db.Model):
    email_address = db.StringProperty(required=True)
    first_name = db.StringProperty(required=True)
    last_name = db.StringProperty(required=True)
    user_name = db.StringProperty()
    password = db.StringProperty()
    is_registered = db.BooleanProperty(required=True,default=False)
    is_admin = db.BooleanProperty(required=True,default=False)
    rego_code = db.StringProperty(required=False)
    google_user = db.UserProperty(required=False)

def get_email(first_name,last_name=None):
    if last_name:
        user = db.Query(SBUser).filter('first_name =',first_name).filter('last_name =',last_name).get()
    else: # treat the first name as a user_name
        user = db.Query(SBUser).filter('user_name =',first_name).get()
    if user:
        return user.email_address
    else:
        return None

def gen_rego_code():
    possibilities = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    output = []
    for i in range(20):
        output.append(random.choice(possibilities))
    return ''.join(output)
    
def authenticate(email,pwd):
    m = md5(pwd).hexdigest()
    return db.Query(SBUser).filter('email_address =',email).filter('password =',m).filter('is_registered =',True).get()

def get_current_user_name():
    sess = sessions.Session()
    if sess.has_key('user'):
        return sess['user']
    #elif users.is_current_user_admin():
    #    return users.get_current_user().nickname()
    return ''

def is_current_user_admin():
    try:
        user_name = sessions.Session()['user']
    except KeyError:
        return False
    # check google account first
    if users.is_current_user_admin():
        return True
    # then check shuttlebugs account
    user = db.Query(SBUser).filter('user_name =',user_name).get()
    if not user:
        return False
    sessions.Session()['admin'] = user.is_admin
    return user.is_admin

def create_login_url(url):
    return '/user/login?target=%s' % url
    
class UserNameMapping(db.Model):
    local_name = db.StringProperty()
    google_user = db.UserProperty()

# Handlers
class ManageUsers(webapp.RequestHandler):
    def get(self):
        data = {
            'pages'     : post.Post.get_pages(),           
            'session'   : sessions.Session(),
            'users'     : list(db.Query(SBUser).order('first_name').order('last_name').fetch(1000))
        }
        return self.response.out.write(unicode(template.render('sbuser/manage.html',data)))
    def post(self):
        sess = sessions.Session()
        if not is_current_user_admin() and not users.is_current_user_admin():
            sess['flash'] = ['You must be an admin to add a user.']
            return self.redirect(self.request.uri)
        email_address = self.request.get('email_address')
        first_name    = self.request.get('first_name')
        last_name     = self.request.get('last_name')
        existing_user = db.Query(SBUser).filter('email_address =',email_address).get()
        if existing_user:
            sess['flash'] = ['User with that email address already exists.']
            return self.redirect(self.request.uri)
        new_user = SBUser(email_address=email_address,first_name=first_name,last_name=last_name,is_admin=True)
        new_user.put()
        sess['flash'] = ['User added.']
        return self.redirect(self.request.uri)
        

class Register(webapp.RequestHandler):    
    def get(self):
        data = {
            'pages'     : post.Post.get_pages(),            
            'session'   : sessions.Session()
        }
        return self.response.out.write(unicode(template.render('sbuser/register.html',data)))
        
    def post(self):
        email_address = self.request.get('email_address')
        user_name = self.request.get('user_name')
        password = self.request.get('password')
        password_again = self.request.get('password_again')
        sess = sessions.Session()
        existing = db.Query(SBUser).filter('email_address =',email_address).get()
        error = False
        flash = []
        if not existing:
            flash.append('This email address is not on the member list')
            error = True
        else:
            if existing.is_registered:
                flash.append('This user has already registered')
                error = True
        if password != password_again:
            flash.append('Your passwords were entered differently')
            error = True      
        if error:
            sess['flash'] = flash
            return self.redirect(self.request.uri)
        sess['user'] = user_name
        sess['flash'] = ['Registration Successful.','You will receive an email with a link you can use to confirm registration.','Logged in.']
        existing.password = md5(password).hexdigest()
        existing.user_name = user_name
        #existing.is_registered = True
        existing.rego_code = gen_rego_code()
        existing.put()
        mail.send_mail(
            sender='Shuttlebugs Website<thecheesun@gmail.com>',
            to='%s %s <%s>' % (existing.first_name, existing.last_name, email_address),
            subject='Confirm Shuttlebugs Website Registration',
            body='''
Hi %s,

Your email account has been activated on the Shuttlebugs Website.

To confirm that everything is working correctly and complete the registration, please visit the following link.

http://sbugsbc.appspot.com/user/confirm?code=%s&email=%s

Regards,
Shuttlebugs
            ''' % (existing.first_name,existing.rego_code,email_address)
        )
        return self.redirect('/')
    
        
class Confirm(webapp.RequestHandler):
    def get(self):
        code = self.request.get('code')
        email = self.request.get('email')
        existing = db.Query(SBUser).filter('rego_code =',code).filter('email_address =',email).get()
        sess = sessions.Session()
        if not existing:
            sess['flash'] = ['Error with confirmation - either email or code was incorrect.']
            return self.redirect('register')
        existing.is_registered = True
        existing.put()
        sess['flash'] = ['Registration Successful!','Logged in.']
        return self.redirect('/')
        

class Logout(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        session = sessions.Session()
        if not 'user' in session:
            session['flash'] = ['Not logged in, cant log out.']
            return self.redirect('/user/login')
        data = {
            'pages'     : post.Post.get_pages(),            
            'session'   : session
        }
        return self.response.out.write(unicode(template.render('sbuser/logout.html',data)))
    
    def post(self):
        session = sessions.Session()
        session['user'] = ''
        session['admin'] = False
        session['flash'] = ['Logged out.']
        return self.redirect('/')
        
class Login(webapp.RequestHandler):
    def get(self):
        user = users.get_current_user()
        target = self.request.get('target')
        session = sessions.Session()
        data = {
            'pages'     : post.Post.get_pages(),            
            'session'   : session,
            'target'    : target
        }
        return self.response.out.write(unicode(template.render('sbuser/login.html',data)))
    
    def post(self):
        session = sessions.Session()
        if users.is_current_user_admin():
            session['user'] = 'root' #users.get_current_user().nickname()
            session['admin'] = True
            session['flash'] = ['Login successful.']
            return self.redirect('/')
        email       = self.request.get('email')
        password    = self.request.get('password')
        target      = self.request.get('target')
        sbu         = authenticate(email,password)
        if sbu:
            session['user'] = sbu.user_name
            session['admin'] = sbu.is_admin
            session['flash'] = ['Login successful.']
        else:
            session['flash'] = ['Login failed.']
            if target:
                return self.redirect(create_login_url(target))
            return self.redirect('/user/login')
        if target:
            return self.redirect(target)
        return self.redirect('/')

class SetAlias(webapp.RequestHandler):
    
    def __compose(self,messages=[]):
        user = users.get_current_user()
        login_details = create_login_details(user)
        if not user:
            return self.redirect(users.create_login_url(self.request.uri))
        existing_mapping = db.Query(UserNameMapping).filter('google_user = ',user).get()
        
        current_alias = None
        if existing_mapping:
            current_alias = existing_mapping.local_name
        
        data = {
            'messages'      : messages,
            'login'         : login_details,
            'current_alias' : current_alias,
            'pages'         : post.Post.get_pages()
        }
        return self.response.out.write(unicode(template.render('sbuser/alias.html',data)))        
    
    def get(self):
        return self.__compose()
            
    def post(self):
        local_name = self.request.get('local_name')
        current_user = users.get_current_user()
        if not current_user:
            return self.redirect(users.create_login_url(self.request.uri))
        
        if not local_name:
            return self.__compose(['No new name specified.'])
        
        #check if the desired name is already in use
        check_mapping = db.Query(UserNameMapping).filter('local_name =',local_name).get()
        if check_mapping:
            return self.__compose(['Someone else (%s) is already known as %s' % (check_mapping.google_user,local_name)])
        
        existing_mapping = db.Query(UserNameMapping).filter('google_user = ',current_user).get()
        if existing_mapping:
            existing_mapping.local_name = local_name
            existing_mapping.put()
        else:
            new_mapping = UserNameMapping(local_name=local_name,google_user=current_user)
            new_mapping.put()
        return self.__compose(['Changed your alias successfully'])

# Other Functions    
def get_username_mapping(user):
    mapped = db.Query(UserNameMapping).filter('google_user = ',user).get()
    if mapped:
        return mapped.local_name
    return user.nickname()


def create_login_details():
    sess = sessions.Session()
    user = None
    google_user = users.get_current_user()      
    if sess.has_key('user'):
        user = db.Query(SBUser).filter('user_name =',sess['user']).get()
    elif google_user:
        user = db.Query(SBUser).filter('google_user =',google_user).get()
    if user:
        login_details = {
            'name'  :   user.user_name,
            'admin' :   user.is_admin
        }
        return login_details
      
    return None

'''    
def create_login_details(user):
    if user:
        login_details = {
            'name'  : get_username_mapping(user), #user.nickname(),
            'url'   : users.create_logout_url('/'),
        }
        if users.is_current_user_admin():
            login_details['admin'] = True
        else:
            login_details['admin'] = False
        return login_details
    return None
'''
