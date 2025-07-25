from PyQt5 import QtWidgets, QtGui, QtCore
import sys
import cv2
import gesture
import transfer
import threading
import os
import io
from PIL import ImageGrab, Image
import numpy as np

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Grab Transfer")
        self.setGeometry(100, 100, 800, 600)
        # Webcam preview label
        self.label = QtWidgets.QLabel(self)
        self.label.setAlignment(QtCore.Qt.AlignCenter)
        self.setCentralWidget(self.label)

        # Status label for grab gesture
        self.status_label = QtWidgets.QLabel("", self)
        self.status_label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)
        self.status_label.setStyleSheet("font-size: 24px; color: red; background: rgba(255,255,255,0.7);")
        self.status_label.setGeometry(0, 0, 800, 40)
        self.status_label.raise_()

        # Receive Files button
        self.receive_btn = QtWidgets.QPushButton("Receive Screenshot", self)
        self.receive_btn.setGeometry(10, 50, 180, 40)
        self.receive_btn.clicked.connect(self.start_server_thread)

        # OpenCV video capture
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            self.label.setText("Could not open webcam.")
        else:
            # Timer to update frames
            self.timer = QtCore.QTimer()
            self.timer.timeout.connect(self.update_frame)
            self.timer.start(30)  # ~33 FPS

        self.prev_grab = False
        self.screenshot = None
        self.server_thread = None
        self.broadcast_thread = None
        self.broadcast_stop_event = None
        self.sending = False

    def start_server_thread(self):
        if self.server_thread and self.server_thread.is_alive():
            QtWidgets.QMessageBox.information(self, "Server", "Server is already running.")
            return
        save_dir = QtWidgets.QFileDialog.getExistingDirectory(self, "Select Folder to Save Screenshots")
        if not save_dir:
            return
        # Start UDP broadcast for device discovery
        if self.broadcast_thread and self.broadcast_thread.is_alive():
            if self.broadcast_stop_event:
                self.broadcast_stop_event.set()
        self.broadcast_stop_event = threading.Event()
        self.broadcast_thread = threading.Thread(target=transfer.broadcast_presence, args=(5001, self.broadcast_stop_event), daemon=True)
        self.broadcast_thread.start()
        self.server_thread = threading.Thread(target=self.run_server, args=(save_dir,), daemon=True)
        self.server_thread.start()
        QtWidgets.QMessageBox.information(self, "Server", "Server started. Waiting for screenshots...")

    def run_server(self, save_dir):
        try:
            filepath = transfer.start_server(save_dir)
            # Display the received screenshot
            self.show_received_image(filepath)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Server Error", str(e))
        finally:
            if self.broadcast_stop_event:
                self.broadcast_stop_event.set()

    def show_received_image(self, filepath):
        img = Image.open(filepath)
        img = img.convert("RGB")
        img = img.resize((600, 400))
        data = img.tobytes("raw", "RGB")
        qimg = QtGui.QImage(data, img.width, img.height, QtGui.QImage.Format_RGB888)
        pixmap = QtGui.QPixmap.fromImage(qimg)
        # Show in a popup window
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle("Received Screenshot")
        vbox = QtWidgets.QVBoxLayout()
        lbl = QtWidgets.QLabel()
        lbl.setPixmap(pixmap)
        vbox.addWidget(lbl)
        dlg.setLayout(vbox)
        dlg.exec_()

    def update_frame(self):
        ret, frame = self.cap.read()
        if ret:
            frame, hand_detected, grab_detected = gesture.process_frame(frame)
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            bytes_per_line = ch * w
            qt_image = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
            pixmap = QtGui.QPixmap.fromImage(qt_image)
            self.label.setPixmap(pixmap.scaled(self.label.size(), QtCore.Qt.KeepAspectRatio))
            # Grab/release logic
            if grab_detected and not self.prev_grab:
                self.status_label.setText("Grab Detected! Screenshot taken.")
                self.screenshot = self.take_screenshot()
            elif not grab_detected and self.prev_grab and self.screenshot is not None and not self.sending:
                self.status_label.setText("Release Detected! Discovering receivers...")
                self.sending = True
                QtCore.QTimer.singleShot(100, self.send_screenshot_discovery)
            elif not grab_detected:
                self.status_label.setText("")
            self.prev_grab = grab_detected
        else:
            self.label.setText("Failed to grab frame.")

    def take_screenshot(self):
        img = ImageGrab.grab()
        return img

    def send_screenshot_discovery(self):
        if self.screenshot is None:
            self.status_label.setText("")
            self.sending = False
            return
        # Discover receivers
        receivers = transfer.discover_receivers(timeout=3)
        if not receivers:
            self.status_label.setText("No receivers found!")
            QtCore.QTimer.singleShot(2000, lambda: self.status_label.setText(""))
            self.sending = False
            return
        # If multiple receivers, let user pick
        if len(receivers) > 1:
            items = [f"{ip}:{port}" for ip, port in receivers]
            item, ok = QtWidgets.QInputDialog.getItem(self, "Select Receiver", "Receivers:", items, 0, False)
            if not ok or not item:
                self.status_label.setText("")
                self.sending = False
                return
            ip, port = item.split(":")
            ip = ip.strip()
            port = int(port)
        else:
            ip, port = receivers[0]
        # Save screenshot to a temporary file
        tmp_path = os.path.join(os.getcwd(), "_grab_screenshot.png")
        self.screenshot.save(tmp_path)
        threading.Thread(target=self.send_file, args=(tmp_path, ip, port), daemon=True).start()

    def send_file(self, filepath, ip, port):
        try:
            transfer.send_file(filepath, ip, port)
            self.status_label.setText("Screenshot sent!")
        except Exception as e:
            self.status_label.setText(f"Send failed: {e}")
        QtCore.QTimer.singleShot(2000, lambda: self.status_label.setText(""))
        self.sending = False
        # Optionally remove the temp screenshot file
        try:
            os.remove(filepath)
        except Exception:
            pass

    def closeEvent(self, event):
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
        if self.broadcast_stop_event:
            self.broadcast_stop_event.set()
        event.accept()

def run_app():
    app = QtWidgets.QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 