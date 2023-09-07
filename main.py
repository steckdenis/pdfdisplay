from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *

import qrcode
import cherrypy
import poppler

import socket
import threading
import os
import sys
import struct
import urllib
import json

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

    def render_page(self, page_index, preview):
        if page_index >= self.doc.pages:
            page_index = self.doc.pages - 1

        # Render the pages
        renderer = poppler.PageRenderer()

        page = self.doc.create_page(page_index)
        page_rect = page.page_rect()
        pwidth = page_rect.width            # Width and height in points (1/72nd of an inch)
        pheight = page_rect.height

        if preview:
            if self.processing:
                # Render the page at DPI sufficiently high for people to be able to read text
                xdpi = 72
                ydpi = 72
            else:
                # Render the page at some low DPI, just for preview
                xdpi = 40
                ydpi = 40
        else:
            size = self.label.size()
            swidth = size.width()               # Screen size in pixels
            sheight = size.height()

            xdpi = swidth / (pwidth / 72)       # dot-per-inch = pixels / inch = pixels / (points / 72)
            ydpi = sheight / (pheight / 72)

        image = renderer.render_page(page, xdpi, ydpi)
        image = QImage(image.data, image.width, image.height, image.bytes_per_row, QImage.Format_RGB32)
        image = image.copy()                # Required because renderer.render_page will go away, freeing the data used as QImage as backing store.

        return image

    @cherrypy.expose
    def index(self):
        with open("templates/index.html", "rb") as f:
            return f.read()

    @cherrypy.expose
    def upload_pdf(self, data, processing):
        # Load the PDF with Poppler
        self.doc = poppler.load_from_data(data.file.read())
        self.processing = (processing == 'true')

        # For processing: extract lines from the PDF and split them in half if they are too long
        self.page_lines = []

        if self.processing:
            for page_index in range(self.doc.pages):
                page = self.doc.create_page(page_index)
                tops_to_lines = {}

                for element in page.text_list():    # Roughly words with coordinates
                    top = element.bbox.top

                    if top not in tops_to_lines:
                        tops_to_lines[top] = []

                    tops_to_lines[top].append(element)

                # We now have a set of lines (words sharing the same top coordinate). Create a list of these and sort by top value
                for top in tops_to_lines.keys():
                    tops_to_lines[top] = sorted(tops_to_lines[top], key=lambda e: e.bbox.left)

                tops_to_lines = sorted(tops_to_lines.items(), key=lambda e: e[0])

                # Split the lines and go from lists of poppler text elements to nice dicts
                # NOTE: Lines not split for the moment
                for i in range(len(tops_to_lines)):
                    top, elements = tops_to_lines[i]
                    left = elements[0].bbox.left
                    bottom = top + elements[0].bbox.height
                    right = elements[-1].bbox.left + elements[-1].bbox.width
                    width = right - left
                    height = bottom - top
                    text = ' '.join([e.text for e in elements])

                    # Cleanup the text
                    text = text \
                        .replace('R/', '') \
                        .replace('1.', '') \
                        .replace('2.', '') \
                        .replace('3.', '') \
                        .replace('4.', '') \
                        .replace('5.', '') \
                        .replace('6.', '') \
                        .strip()

                    tops_to_lines[i] = {    # Preview DPI is 72, which is also the numbers of points per inch (the unit used here). So no need to transform from points to pixels
                        "top": int(top),
                        "left": int(left),
                        "width": int(width),
                        "height": int(height),
                        "text": text
                    }

                self.page_lines.append(tops_to_lines)


        return str(self.doc.pages)

    @cherrypy.expose
    def get_page_image(self, page_index):
        """ Get the image of a page in the PDF. This is always a page from the original PDF, whether processing is enabled or not
        """
        page_index = int(page_index)
        img = self.render_page(page_index, preview=True)

        # Save img as PNG and return that data
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)

        img.save(buf, "PNG")

        cherrypy.response.headers['Content-Type'] = 'image/png'
        cherrypy.response.headers['Cache-Control'] = 'no-store'
        return bytes(ba)

    @cherrypy.expose
    def get_pagelines(self):
        cherrypy.response.headers['Content-Type'] = 'application/json'
        return bytes(json.dumps(self.page_lines), 'utf-8')

    @cherrypy.expose
    def set_page(self, page_index):
        # Tell the GUI to display that image
        page_index = int(page_index)
        img = self.render_page(page_index, preview=False)

        pix = QPixmap.fromImage(img)

        self.label.setPixmap(pix)
        self.qrcode.hide()

        return ''

    @cherrypy.expose
    def set_line(self, page_index, line_index):
        page_index = int(page_index)
        line_index = int(line_index)

        try:
            # Get the line and display it in the QLabel (that has the right background color and font)
            line = self.page_lines[page_index][line_index]["text"]

            # If the line is too long, split it close to the middle at some punctuation
            print(line, len(line))
            if len(line) > 55:
                l = len(line)
                middle = l // 2
                distances_and_indexes = []

                for index, c in enumerate(line):
                    if c in '!,.;:':
                        distances_and_indexes.append((abs(index - middle), index))

                distances_and_indexes = sorted(distances_and_indexes, key = lambda e: e[0])

                if len(distances_and_indexes) > 0:
                    split_after_index = distances_and_indexes[0][1]

                    line = line[:split_after_index+1] + '\n' + line[split_after_index+1:]

            self.label.setText(line)
            self.qrcode.hide()
        except IndexError:
            pass

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
    win.setWindowFlags(Qt.WindowType.FramelessWindowHint)
    win.setWindowTitle("PDF Display")
    win.setCursor(Qt.CursorShape.BlankCursor)
    win.setScaledContents(True)
    win.setAlignment(Qt.AlignCenter)
    win.setWordWrap(True)
    win.resize(800, 600)
    win.showFullScreen()

    # Now that the main window is shown and has a size, we can compute the ideal font size
    QFontDatabase.addApplicationFont("Cantarell-Bold.ttf")
    app.processEvents()

    font = QFont("Cantarell-Bold", int(win.width() / 20))
    palette = QPalette(QColor(255, 255, 255), QColor(0, 0, 0))
    win.setFont(font)
    win.setPalette(palette)

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

    # Start the webserver thread
    webserver_thread = WebserverThread(win, label)
    webserver_thread.start()

    app.exec()
