from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PyQt6.QtWidgets import *

import qrcode
import socket
import threading
import sys
import struct

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

def recv(f):
    data = f.read(4)
    data_len = struct.unpack('>i', data)[0]

    data = b""
    got_len = 0

    while got_len < data_len:
        packet = f.read(4096)
        data += packet
        got_len += len(packet)

    return data

class ImageThread(threading.Thread):
    def __init__(self, label, qrcode):
        super().__init__(daemon=True)
        self.label = label
        self.qrcode = qrcode

    def run(self):
        while True:
            # Receive a PNG file over stdin
            print('Waiting for a filename')
            filename = input()
            print('Got a filename', filename)
            self.label.setPixmap(QPixmap(filename))
            self.qrcode.hide()

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

    # Start the image thread
    image_thread = ImageThread(win, label)
    image_thread.start()

    app.exec()
