from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.api import images
from post import Post
from appengine_utilities import sessions
from django.template.defaultfilters import slugify
from sbuser import get_current_user_name, create_login_url

from datetime import date
import random

# models

class Gallery(db.Model):
    title = db.StringProperty()
    slug = db.StringProperty()
    date = db.DateTimeProperty(auto_now_add=True)
    description = db.TextProperty()
    disabled = db.BooleanProperty(default=False)

    # override put() to auto populate some fields
    def put(self,*args,**kw):
        self.slug = slugify(self.title)
        return db.Model.put(self,*args,**kw)
    
class Photo(db.Model):
    title = db.StringProperty()
    description = db.TextProperty()
    filename = db.StringProperty()
    extension = db.StringProperty()
    image_data = db.BlobProperty()
    thumb_data = db.BlobProperty()
    gallery = db.ReferenceProperty(Gallery,collection_name='photos')
    frontpage = db.BooleanProperty(default=False)

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

class GallerySWF(webapp.RequestHandler):
    def get(self,gallery):
        gallery = db.Query(Gallery).filter("slug =",gallery).get()
        data = {
            'pages'     : Post.get_pages(),
            'session'   : sessions.Session(),
        }
        if not gallery:
            self.error(404)
            return self.response.out.write(unicode(template.render('404.html',data)))
        data['gallery'] = gallery
        data['photos'] = [ {'id':photo.key().id(), 'caption':photo.title} for photo in gallery.photos ]
        self.response.headers['Content-Type'] = "application/x-shockwave-flash"
        return self.response.out.write(unicode(open('static/main.css','r').read()))
        
class ImagesXML(webapp.RequestHandler):
    def get(self,gallery):
        gallery = db.Query(Gallery).filter("slug =",gallery).get()
        data = {
            'pages'     : Post.get_pages(),
            'session'   : sessions.Session(),
        }
        if not gallery:
            self.error(404)
            return self.response.out.write(unicode(template.render('404.html',data)))
        data['gallery'] = gallery
        data['photos'] = [ {'id':photo.key().id(), 'caption':photo.title, 'ext':photo.extension} for photo in gallery.photos ]
        self.response.headers['Content-Type'] = "text/xml"
        return self.response.out.write(unicode(template.render('photos/images.xml',data)))

class GetThumb(webapp.RequestHandler):
    def get(self,gallery,id,ext):
        image = Photo.get_by_id(int(id))
        if not image or image.gallery.slug != gallery:
            return self.error(404)
        if image.extension == 'png':
            mime_type = 'png'
        elif image.extension == 'jpg':
            mime_type = 'jpeg'
        self.response.headers['Content-Type'] = "image/%s" % mime_type
        self.response.headers['Cache-Control'] = "max-age=31536000"
        return self.response.out.write(str(image.thumb_data))

class GetImage(webapp.RequestHandler):
    def get(self,gallery,id,ext):
        image = Photo.get_by_id(int(id))
        if not image or image.gallery.slug != gallery:
            return self.error(404)
        if image.extension == 'png':
            mime_type = 'png'
        elif image.extension == 'jpg':
            mime_type = 'jpeg'
        self.response.headers['Content-Type'] = "image/%s" % mime_type
        self.response.headers['Cache-Control'] = "max-age=31536000"
        return self.response.out.write(str(image.image_data))

class ManageGalleries(webapp.RequestHandler):
    def _compose(self,flash=[]):
        sess = sessions.Session()
        sess['flash'] = flash
        galleries = [{'id': gallery.key().id(), 'slug': gallery.slug, 'date': gallery.date, 'title': gallery.title, 'description': gallery.description } for gallery in db.Query(Gallery).filter('disabled =', False).order('date').fetch(100)]
        disabled = [{'id': gallery.key().id(), 'slug': gallery.slug, 'date': gallery.date, 'title': gallery.title, 'description': gallery.description } for gallery in db.Query(Gallery).filter('disabled =', True).order('date').fetch(100)]      
        data = {
            'pages'     : Post.get_pages(),
            'session'   : sess,
            'galleries' : galleries,
            'disabled'  : disabled
        }
        return self.response.out.write(unicode(template.render('photos/index.html',data)))
    def get(self):
        return self._compose()
    @login_required
    def post(self):
        action = self.request.get('action')
        if action in ['enable','disable']:
            gallery_id = self.request.get('id')
            g = Gallery.get_by_id(int(gallery_id))
            g.disabled = (action == 'disable')
            g.put()
            return self._compose(['Gallery succesfully %sd.' % action])
        elif action == 'add':
            title = self.request.get('title')
            description = self.request.get('description')
            new_gallery = Gallery(title=title,description=description)
            new_gallery.put()
            return self._compose(['Gallery "%s" succesfully created.' % title])

class QuickUpload(webapp.RequestHandler):
    def _compose(self,gallery_slug,flash=[]):
        gallery = db.Query(Gallery).filter('slug =',gallery_slug).get()
        sess = sessions.Session()
        sess['flash'] = flash        
        data = {
            'session'   : sess,
            'pages'     : Post.get_pages(),
            'title'     : gallery.title,
            'photos'    : [ {'id':photo.key().id(), 'caption':photo.title, 'ext':photo.extension, 'fp':photo.frontpage} for photo in gallery.photos ],
        }
        return self.response.out.write(unicode(template.render('photos/upload.html',data)))        

    @login_required
    def get(self,gallery_slug):
        return self._compose(gallery_slug)

    @login_required    
    def post(self,gallery_slug):
        action = self.request.get("action")
        if action == 'delete':
            photo_id = self.request.get("id")
            p = Photo.get_by_id(int(photo_id))
            p.delete()
            return self._compose(gallery_slug,['Delete Successful'])
        elif action == 'frontpage':
            photo_id = self.request.get("id")
            new_setting = self.request.get("frontpage")
            p = Photo.get_by_id(int(photo_id))
            p.frontpage = (new_setting == 'include')
            p.put()
            return self._compose(gallery_slug,['Edit Successful'])
        elif action  == 'add':
            try:
                image = images.Image(self.request.get("img"))
                thumb = images.Image(self.request.get("img"))
                aspect_ratio = float(image.width) / float(image.height)
                # crop the image to make it square for the thumb
                if aspect_ratio > 1.0:
                    left_x = float(image.width-image.height)/float(2*image.width)
                    right_x = float(image.height+image.width)/float(2*image.width)
                    thumb.crop(left_x,0.0,right_x,1.0)
                elif aspect_ratio < 1.0:
                    top_y = float(image.height-image.width)/float(2*image.height)
                    bottom_y = float(image.height+image.width)/float(2*image.height)
                    thumb.crop(0.0,top_y,1.0,bottom_y)
                thumb.resize(45,45)
                image.resize(800,600)
                #find gallery that we are adding to
                gallery = db.Query(Gallery).filter('slug =',gallery_slug).get()
                # is the photo to be displayed on the front page as well?
                fp = self.request.get("frontpage",False)
                if fp:
                    fp = True                
                # create and save the new photo
                new_photo = Photo(
                    title = self.request.get("title"),
                    image_data = db.Blob(image.execute_transforms()),
                    thumb_data = db.Blob(thumb.execute_transforms()),
                    extension = 'png',
                    gallery = gallery,
                    frontpage = fp
                )
                new_photo.put()
                #return self.response.out.write('<img src="%s_thumb.%s"></img>' % (new_photo.key().id(),new_photo.extension))
                return self._compose(gallery_slug,['Upload Successful'])
            except Exception, e:
                return self._compose(gallery_slug,['Upload Failed', str(e)])

class ViewGallery(webapp.RequestHandler):
    def _compose(self,gallery_slug,flash=[]):
        sess = sessions.Session()
        sess['flash'] = flash
        gallery = db.Query(Gallery).filter('slug =',gallery_slug).get()
        data = {
            'pages'     : Post.get_pages(),
            'session'   : sess,
            'gallery'   : gallery,
        }
        if not gallery:
            self.error(404)
            return self.response.out.write(unicode(template.render('404.html',data)))
        return self.response.out.write(unicode(template.render('photos/gallery.html',data)))
    
    def get(self,gallery):
        return self._compose(gallery)
    
    @login_required
    def post(self,gallery_slug):
        image = images.Image(self.request.get("img"))
        thumb = images.Image(self.request.get("img"))
        aspect_ratio = float(image.width) / float(image.height)
        # crop the image to make it square for the thumb
        if aspect_ratio > 1.0:
            left_x = float(image.width-image.height)/float(2*image.width)
            right_x = float(image.height+image.width)/float(2*image.width)
            thumb.crop(left_x,0.0,right_x,1.0)
        elif aspect_ratio < 1.0:
            top_y = float(image.height-image.width)/float(2*image.height)
            bottom_y = float(image.height+image.width)/float(2*image.height)
            thumb.crop(0.0,top_y,1.0,bottom_y)
        thumb.resize(45,45)
        image.resize(800,600)
        # find gallery that we are adding to
        gallery = db.Query(Gallery).filter('slug =',gallery_slug).get()
        # is the photo to be displayed on the front page as well?
        fp = self.request.get("frontpage",False)
        if fp:
            fp = True
        # create and save the new photo
        new_photo = Photo(
            title = self.request.get("title"),
            image_data = db.Blob(image.execute_transforms()),
            thumb_data = db.Blob(thumb.execute_transforms()),
            extension = 'png',
            gallery = gallery,
            frontpage = fp,
        )
        new_photo.put()
        #self.redirect('/gallery/%s/view'%gallery_slug) 
        return self._compose(gallery_slug,['New photo "%s" added to gallery "%s".'%(new_photo.title,gallery.title)])

# Other Functions
def pic_of_day_widget():
    ''' gets a random picture from one of the galleries, based on the date '''
    
    today = date.today()
    
    random.seed((today.year,today.month,today.day))
    
    pics = db.Query(Photo,keys_only=True).filter('frontpage = ',True).fetch(1000)
    
    try:
        chosen_id = random.choice(pics).id()
    except IndexError:
        return '<p>No gallery images</p>'
    
    photo = Photo.get_by_id(int(chosen_id))
    
    data = {
        'gallery'   : photo.gallery.slug,
        'id'        : chosen_id,
        'extension' : photo.extension,
        'title'     : photo.title,
        }
    
    return template.render('photos/polaroid.html',data)

