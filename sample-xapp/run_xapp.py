from xapp_control import *
from xapp_threading import *


def ThreadInit():
    thread1 = Thread(target=KpmDecodeThread, )
    thread2 = Thread(target=KpmUpdateThread, )
    thread3 = Thread(target=RLThread, )

    thread1.start()
    thread2.start()
    thread3.start()

def main():
    global RicMsg   # handover command queue
    global RLInput, UnDecode, Decoded, receivedReports
    
    # # configure logger and console output
    # logging.basicConfig(level=logging.DEBUG, filename='/home/xapp-logger.log', filemode='a+',
    #                     format='%(asctime)-15s %(levelname)-8s %(message)s')
    # formatter = logging.Formatter('%(asctime)-15s %(levelname)-8s %(message)s')
    # console = logging.StreamHandler()
    # console.setLevel(logging.INFO)
    # console.setFormatter(formatter)
    # logging.getLogger('').addHandler(console)
    
    control_sck = open_control_socket(4200)
    ThreadInit()

    while True:

        data_sck = receive_from_socket(control_sck)
        if len(data_sck) <= 0:
            if len(data_sck) == 0:
                continue
            else:
                # logging.info('Negative value for socket')
                break
        else:

            UnDecode.put(data_sck)

        if not RicMsg.empty():
            msg = RicMsg.get()
            imsi, target = msg[0], msg[1]
            msg = f"{imsi},{target}"
            send_socket(control_sck, msg)

            
            # RicMsg = q.Queue(-1)
            with UnDecode.mutex:
                UnDecode.queue.clear()
            with Decoded.mutex:
                Decoded.queue.clear()
            with RLInput.mutex:
                RLInput.queue.clear()
            # UnDecode, Decoded = q.Queue(-1), q.Queue(-1)
            receivedReports[:] = False

if __name__ == '__main__':
    main()

