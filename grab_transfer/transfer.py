import socket
import os
import threading
import time

BUFFER_SIZE = 4096
SEPARATOR = '<SEPARATOR>'
DISCOVERY_PORT = 5002
DISCOVERY_MESSAGE = b'GRAB_TRANSFER_RECEIVER'

# Server: Receive file
def start_server(save_dir, host='0.0.0.0', port=5001):
    s = socket.socket()
    s.bind((host, port))
    s.listen(1)
    print(f"[*] Listening as {host}:{port}")
    conn, addr = s.accept()
    print(f"[+] {addr} is connected.")
    # Receive file info
    received = conn.recv(BUFFER_SIZE).decode()
    filename, filesize = received.split(SEPARATOR)
    filename = os.path.basename(filename)
    filesize = int(filesize)
    filepath = os.path.join(save_dir, filename)
    # Receive file data
    with open(filepath, 'wb') as f:
        bytes_read = 0
        while bytes_read < filesize:
            bytes_chunk = conn.recv(BUFFER_SIZE)
            if not bytes_chunk:
                break
            f.write(bytes_chunk)
            bytes_read += len(bytes_chunk)
    conn.close()
    s.close()
    print(f"[+] File received: {filepath}")
    return filepath

# Client: Send file
def send_file(filepath, target_ip, port=5001):
    filesize = os.path.getsize(filepath)
    s = socket.socket()
    s.connect((target_ip, port))
    # Send file info
    s.send(f"{os.path.basename(filepath)}{SEPARATOR}{filesize}".encode())
    # Send file data
    with open(filepath, 'rb') as f:
        while True:
            bytes_read = f.read(BUFFER_SIZE)
            if not bytes_read:
                break
            s.sendall(bytes_read)
    s.close()
    print(f"[+] File sent: {filepath}")

# Receiver: Broadcast presence for discovery
def broadcast_presence(port=5001, stop_event=None):
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    message = f"{DISCOVERY_MESSAGE.decode()}|{port}".encode()
    while not (stop_event and stop_event.is_set()):
        udp_sock.sendto(message, ("<broadcast>", DISCOVERY_PORT))
        time.sleep(1)
    udp_sock.close()

# Sender: Listen for receivers on the network
def discover_receivers(timeout=3):
    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    udp_sock.bind(("", DISCOVERY_PORT))
    udp_sock.settimeout(timeout)
    receivers = set()
    start = time.time()
    try:
        while time.time() - start < timeout:
            try:
                data, addr = udp_sock.recvfrom(1024)
                if data.startswith(DISCOVERY_MESSAGE):
                    parts = data.decode().split("|")
                    if len(parts) == 2:
                        receivers.add((addr[0], int(parts[1])))
            except socket.timeout:
                break
    finally:
        udp_sock.close()
    return list(receivers) 