import socket
import logging
import struct

# open control socket
def open_control_socket(port: int):

    print('Waiting for xApp connection on port ' + str(port))

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # host = socket.gethostname()
    # bind to INADDR_ANY
    server.bind(('', port))

    server.listen(10)

    control_sck, client_addr = server.accept()
    print('xApp connected: ' + client_addr[0] + ':' + str(client_addr[1]))
    return control_sck


# send through socket
def send_socket(sock, msg: str):
    payload = msg.encode('utf-8')
    sock.sendall(payload)
    print('Socket sent ' + str(len(payload)) + ' bytes')


# receive data from socker
# def receive_from_socket(socket) -> str:

#     ack = 'Indication ACK\n'

#     data = socket.recv(4096)

#     try:
#         print(f'Raw data: {data}')
#         data = data.decode('utf-8')
#         print(f'Hex data: {data}')
#     except UnicodeDecodeError:
#         return ''

#     if ack in data:
#         data = data[len(ack):]

#     if len(data) > 0:
#         print(f'data {data}, dataStrip: {data.strip()}')
#         return data.strip()
#     else:
#         return ''
def _recv_exact(sock, size: int) -> bytes:
    """Receive exactly *size* bytes, or return b'' after a disconnect."""
    chunks = []
    remaining = size
    while remaining:
        chunk = sock.recv(remaining)
        if not chunk:
            return b''
        chunks.append(chunk)
        remaining -= len(chunk)
    return b''.join(chunks)


def receive_from_socket(sock) -> bytes:
    size_data = _recv_exact(sock, 4)
    if not size_data:
        return b''

    data_size = struct.unpack('!I', size_data)[0]
    if data_size == 0:
        return b''

    return _recv_exact(sock, data_size)
