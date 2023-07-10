import cherrypy
import jinja2
import os
import sys
import urllib
import atexit
import subprocess

from urllib.request import urlopen

# Open the GUI
def gui_cleanup():
    global gui
    gui.terminate()

def image_filename(page_index):
    return "/tmp/image_%s.png" % str(page_index)

atexit.register(gui_cleanup)

class Root(object):
    def __init__(self):
        super().__init__()

        # Initialize the Jinja templates
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates"),
            autoescape=jinja2.select_autoescape()
        )

    @cherrypy.expose
    def index(self):
        return self.env.get_template("index.html").render()

    @cherrypy.expose
    def upload_page(self, data, page_index):
        # Save the data URI in a file
        with urllib.request.urlopen(data) as response:
            contents = response.read()

            with open(image_filename(page_index), "wb") as f:
                f.write(contents)

        return page_index

    @cherrypy.expose
    def set_page(self, page_index):
        # Tell the GUI to display that image
        print(image_filename(page_index), file=gui.stdin)
        gui.stdin.flush()
        return ''

if __name__ == '__main__':
    # Open the GUI
    gui = subprocess.Popen([sys.executable, "gui.py"], stdin=subprocess.PIPE, text=True)

    cherrypy.config.update({
        'server.socket_host': '0.0.0.0',
        'server.socket_port': 8080,
    })

    cherrypy.quickstart(Root(), '/', {
        '/static': {
            'tools.staticdir.on': True,
            'tools.staticdir.dir': os.path.abspath('./static/')
        }
    })
