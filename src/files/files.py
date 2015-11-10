from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from post import Post
from appengine_utilities import sessions
from django.template.defaultfilters import slugify
from sbuser import get_current_user_name, create_login_url
import mimetypes

# models
class File(db.Model):
    filename = db.StringProperty()
    extension = db.StringProperty()
    data = db.BlobProperty()
    path = db.StringProperty()

# Helpers
def login_required(funct):
    def new_funct(self,*args,**kw):
        user = get_current_user_name()
        if not user:
            sessions.Session()['flash'] = ['You must login to use this feature.']
            return self.redirect(create_login_url(self.request.uri))
        return funct(self,*args,**kw)
    return new_funct

# handlers
class GetFile(webapp.RequestHandler):
    mime_types = {
        'png'        : 'image/png',
        'jpg'        : 'image/jpeg',
        'pdf'        : 'application/pdf',
        'html'       : 'text/html',
        'default'    : 'text/plain',
        }        
    def get(self,path,name,ext):
        file = File.all().filter('filename =',name).filter('extension =',ext).filter('path =',path).get()
        if not file:
            return self.error(404)
        #try:
        #    mime_type = self.mime_types[file.extension]
        #except KeyError:
        #    mime_type = self.mime_types['default']
        mime_type = mimetypes.guess_type('%s.%s' % (name,ext))[0]
        self.response.headers['Content-Type'] = mime_type
        self.response.headers['Cache-Control'] = "max-age=31536000"
        return self.response.out.write(str(file.data))

class ManageGalleries(webapp.RequestHandler):
    def _compose(self,flash=[]):
        sess = sessions.Session()
        sess['flash'] = flash
        galleries = db.Query(Gallery).order('date').fetch(100)
        data = {
            'pages'     : Post.get_pages(),
            'session'   : sess,
            'galleries' : galleries,
        }
        return self.response.out.write(unicode(template.render('photos/index.html',data)))
    def get(self):
        return self._compose()
    @login_required
    def post(self):
        title = self.request.get('title')
        description = self.request.get('description')
        new_gallery = Gallery(title=title,description=description)
        new_gallery.put()
        return self._compose(['Gallery "%s" succesfully created.' % title])

class ManageFiles(webapp.RequestHandler):
    def _compose(self,flash=[]):
        sess = sessions.Session()
        sess['flash'] = flash        
        data = {
            'session'   : sess,
            'pages'     : Post.get_pages(),
            'files'     : File.all().order('path').order('filename').order('extension').fetch(1000)
        }
        return self.response.out.write(unicode(template.render('files/upload.html',data)))        

    @login_required
    def get(self):
        return self.post()

    @login_required    
    def post(self):
        try:
            action = self.request.get("action")
        except KeyError:
            return self._compose()
            
        if action == 'add':
            try:
                data = self.request.get("file")
                name_parts = self.request.get("filename").split('.')
                path = self.request.get("path").replace("//","/")    
                try:
                    if path[0] == "/":
                        path = path[1:]
                    if path[-1] == "/":
                        path = path[:-1]      
                except IndexError:
                    path = ''              
                # create and save the new file
                new_file = File(
                    filename = name_parts[0],
                    extension = name_parts[1],
                    path = path,
                    data = db.Blob(data),
                    )
                new_file.put()
                return self._compose(['Upload Succesful'])
            except IndexError, e:
                return self._compose(['Upload Failed', 'make sure filename is of the form name.extension'])
            except Exception, e:
                return self._compose(['Upload Failed', str(e)])
        elif action == 'delete':
            try:
                name_parts = self.request.get("filename").split('.')
                path = self.request.get("path")
                file = File.all().filter('filename =',name_parts[0]).filter('extension =',name_parts[1]).filter('path =',path).get()
                file.delete()
                return self._compose(['Delete Succesful'])
            except Exception, e:
                return self._compose(['Delete Failed', str(e)])
        else:
            return self._compose()


