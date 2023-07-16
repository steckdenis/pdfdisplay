from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtWidgets import *
from PyQt6.QtPdf import *

import qrcode
import cherrypy
import jinja2

import socket
import threading
import os
import sys
import struct
import urllib

IMAGES = {}

def get_ip():
    """ https://stackoverflow.com/questions/166506/finding-local-ip-addresses-using-pythons-stdlib
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(0)

        try:
            # doesn't even have to be reachable
            s.connect(('10.254.254.254', 1))
            return s.getsockname()[0]
        except Exception:
            return '127.0.0.1'

class WebserverRoot(object):
    def __init__(self, label, qrcode):
        super().__init__()

        self.label = label
        self.qrcode = qrcode
        self.black_pixmap = QPixmap(64, 64)
        self.black_pixmap.fill(QColor(0, 0, 0))

        # Initialize the Jinja templates
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader("templates"),
            autoescape=jinja2.select_autoescape()
        )

    @cherrypy.expose
    def index(self):
        return self.env.get_template("index.html").render()

    @cherrypy.expose
    def upload_pdf(self, data):
        # Save the PDF document
        with open("/tmp/pdf.pdf", "wb") as f:
            f.write(data.file.read())

        # Load it with Qt
        doc = QPdfDocument(None)
        doc.load("/tmp/pdf.pdf")

        # Render the pages
        size = self.label.size()
        options = QPdfDocumentRenderOptions()
        num_pages = doc.pageCount()

        for page_index in range(num_pages):
            img = doc.render(page_index, size, options)

            IMAGES[page_index] = img

        return str(num_pages)

    @cherrypy.expose
    def get_page_image(self, page_index):
        page_index = int(page_index)
        img = IMAGES[page_index]

        # Save img as PNG and return that data
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)

        img.save(buf, "PNG")

        cherrypy.response.headers['Content-Type'] = 'image/png'
        cherrypy.response.headers['Cache-Control'] = 'no-store'
        return bytes(ba)

    @cherrypy.expose
    def set_page(self, page_index):
        # Tell the GUI to display that image
        page_index = int(page_index)

        if page_index in IMAGES:
            img = IMAGES[page_index]
            pix = QPixmap.fromImage(img)

            self.label.setPixmap(pix)
            self.qrcode.hide()

        return ''

    @cherrypy.expose
    def clear_screen(self):
        # Display solid black instead of a page from the PDF
        self.label.setPixmap(self.black_pixmap)
        self.qrcode.hide()

        return ''

class WebserverThread(threading.Thread):
    def __init__(self, label, qrcode):
        super().__init__(daemon=True)

        self.label = label
        self.qrcode = qrcode

    def run(self):
        # Start the web server and serve
        cherrypy.config.update({
            'server.socket_host': '0.0.0.0',
            'server.socket_port': 8080,
        })

        cherrypy.quickstart(WebserverRoot(self.label, self.qrcode), '/', {
            '/static': {
                'tools.staticdir.on': True,
                'tools.staticdir.dir': os.path.abspath('./static/')
            }
        })

if __name__ == '__main__':
    app = QApplication([])

    # Make the main window, it consists of a background QLabel for displaying images, and the QR-Code
    win = QLabel()
    win.setWindowTitle("PDF Display")
    win.setScaledContents(True)
    win.showMaximized()

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=10,
        border=4
    )
    qr.add_data("http://%s:8080/" % get_ip())
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    label = QLabel(win)
    label.setMinimumSize(img.size[0], img.size[1])

    img.save("/tmp/qrcode.png", "PNG")
    label.setPixmap(QPixmap("/tmp/qrcode.png"))

    layout = QVBoxLayout(win)
    layout.addStretch()
    layout.addWidget(label, 0, Qt.AlignmentFlag.AlignCenter)

    # Load the default background
    win.setPixmap(QPixmap("empty_background.jpg"))

    # Set the main window background to white
    pal = win.palette()
    pal.setColor(QPalette.ColorRole.Window, QColor(255, 255, 255))
    win.setPalette(pal)

    # Start the webserver thread
    webserver_thread = WebserverThread(win, label)
    webserver_thread.start()

    app.exec()
