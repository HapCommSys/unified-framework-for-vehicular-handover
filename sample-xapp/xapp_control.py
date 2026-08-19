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
def send_socket(socket, msg: str):
    bytes_num = socket.send(msg.encode('utf-8'))
    print('Socket sent ' + str(bytes_num) + ' bytes')


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
def receive_from_socket(socket) -> str:
    data_size = 4096
    size_data = socket.recv(4)
    # if len(size_data) < 4:
    #     print("Incomplete size data")
    #     return
    data_size = struct.unpack('!I', size_data)[0]
    # print(f"Expected data size: {data_size} bytes")
    # socket.sendall(b'OK')
    data = socket.recv(data_size)

    return data
