# from xapp_msg_decode import *
import os
from threading import Thread
import struct
from typing import Dict, Optional
# from threshold_HO import *
# from RLmodel import *
import numpy as np
from RLmodel_latest import agent, ckpt, select_action, state_dim
import logging
import time
import sys
import queue as q
import pandas as pd
np.set_printoptions(suppress=True, )

registered_e2_nodes = []
with open("../xapp-sm-connector/init/rsu_list.txt", 'r') as f:
    registered_e2_nodes = [line.strip() for line in f if line.strip()]

# rsu_list.txt contains the LTE anchor first, followed by the mmWave RSUs.
numBS = len(registered_e2_nodes) - 1
if numBS != state_dim[0]:
    raise RuntimeError(
        f'The checkpoint expects {state_dim[0]} mmWave RSUs, but rsu_list.txt '
        f'defines {numBS} (plus one LTE anchor).'
    )

RicMsg = q.Queue(-1)
RLInput = q.Queue(-1)
UnDecode, Decoded = q.Queue(-1), q.Queue(-1)

E2SM_REPORT_MAX_NEIGH = 8
# connectedBS = [1 for i in range(numUE)]
receivedReports = {'CuUp': [0] * numBS, 'CuCp': [0] * numBS, 'Du': [0] * numBS}
receivedReports = pd.DataFrame(receivedReports, index=list(range(2, numBS+2)), dtype=bool)

column = ['2activeVeh', '2SINR', '3SINR-2', '4SINR-2', '5SINR-2', '6SINR-2', '7SINR-2', '8SINR-2', '9SINR-2', '10SINR-2', '11SINR-2',           '2avgLatency', '2numTBInitial', '2numTBRetran', '2numTBQPSK', '2numTB16QAM', '2numTB64QAM',
          '3activeVeh', '2SINR-3', '3SINR', '4SINR-3', '5SINR-3', '6SINR-3', '7SINR-3', '8SINR-3', '9SINR-3', '10SINR-3', '11SINR-3',           '3avgLatency', '3numTBInitial', '3numTBRetran', '3numTBQPSK', '3numTB16QAM', '3numTB64QAM',
          '4activeVeh', '2SINR-4', '3SINR-4', '4SINR', '5SINR-4', '6SINR-4', '7SINR-4', '8SINR-4', '9SINR-4', '10SINR-4', '11SINR-4',           '4avgLatency', '4numTBInitial', '4numTBRetran', '4numTBQPSK', '4numTB16QAM', '4numTB64QAM',
          '5activeVeh', '2SINR-5', '3SINR-5', '4SINR-5', '5SINR', '6SINR-5', '7SINR-5', '8SINR-5', '9SINR-5', '10SINR-5', '11SINR-5',           '5avgLatency', '5numTBInitial', '5numTBRetran', '5numTBQPSK', '5numTB16QAM', '5numTB64QAM',
          '6activeVeh', '2SINR-6', '3SINR-6', '4SINR-6', '5SINR-6', '6SINR', '7SINR-6', '8SINR-6', '9SINR-6', '10SINR-6', '11SINR-6',           '6avgLatency', '6numTBInitial', '6numTBRetran', '6numTBQPSK', '6numTB16QAM', '6numTB64QAM',
          '7activeVeh', '2SINR-7', '3SINR-7', '4SINR-7', '5SINR-7', '6SINR-7', '7SINR', '8SINR-7', '9SINR-7', '10SINR-7', '11SINR-7',           '7avgLatency', '7numTBInitial', '7numTBRetran', '7numTBQPSK', '7numTB16QAM', '7numTB64QAM',
          '8activeVeh', '2SINR-8', '3SINR-8', '4SINR-8', '5SINR-8', '6SINR-8', '7SINR-8', '8SINR', '9SINR-8', '10SINR-8', '11SINR-8',           '8avgLatency', '8numTBInitial', '8numTBRetran', '8numTBQPSK', '8numTB16QAM', '8numTB64QAM',
          '9activeVeh', '2SINR-9', '3SINR-9', '4SINR-9', '5SINR-9', '6SINR-9', '7SINR-9', '8SINR-9', '9SINR', '10SINR-9', '11SINR-9',           '9avgLatency', '9numTBInitial', '9numTBRetran', '9numTBQPSK', '9numTB16QAM', '9numTB64QAM',
          '10activeVeh', '2SINR-10', '3SINR-10', '4SINR-10', '5SINR-10', '6SINR-10', '7SINR-10', '8SINR-10', '9SINR-10', '10SINR', '11SINR-10', '10avgLatency', '10numTBInitial', '10numTBRetran', '10numTBQPSK', '10numTB16QAM', '10numTB64QAM',
          '11activeVeh', '2SINR-11', '3SINR-11', '4SINR-11', '5SINR-11', '6SINR-11', '7SINR-11', '8SINR-11', '9SINR-11', '10SINR-11', '11SINR', '11avgLatency', '11numTBInitial', '11numTBRetran', '11numTBQPSK', '11numTB16QAM', '11numTB64QAM']
Input = dict.fromkeys(column)
Input = pd.Series(Input, dtype=float)

cellId_imsi = {}  # cellId: imsi

def KpmDecodeThread ():

    while True:
        msg = UnDecode.get()
        msg = deserialize_map(msg)
        # for key, value in msg.items():
        #     print(f"{key}: {value}")
        # print(f'RECEIVED REPORT: {msg.get("cellId")} reported {msg.get("type")} at {msg.get("timestamp")}')
        Decoded.put(msg)
        
def KpmUpdateThread ():
    
    try:
        os.remove('/home/xapp-input.log')
    except FileNotFoundError:
        pass
    inputlogger = logging.getLogger('xappinput_logger')
    # fh3 = logging.FileHandler(f'/home/xapp-input_{time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime())}.log')
    fh3 = logging.FileHandler(f'/home/xapp-input.log')
    fh3.setFormatter(logging.Formatter('%(message)s'))
    inputlogger.addHandler(fh3)
    inputlogger.setLevel(logging.INFO)
    inputlogger.info(f"Input features: timestamp, {column}")

    while True:
        report = Decoded.get()
        try:
            cellId = int(report.get("cellId"))
            # print(f'cellId = {cellId}')
        except (TypeError, ValueError):
            print(f"Invalid cellId in report: {report.get('cellId')}")
            print(f"Full report: {report}")
            
        if cellId in list(range(2, numBS+2)):
            timestamp = float(report.get("timestamp"))
            if report.get("type") == "CuUp":
                receivedReports.at[cellId, 'CuUp'] = True

                Input[f'{cellId}avgLatency'] = float(report.get("pdcpLatency", 0.0))

            elif report.get("type") == "CuCp":
                activeVeh = int(report.get("numActiveUes"))
                if activeVeh != 1 and activeVeh != 0:
                    print(f"Warning: cellId {cellId} reports {activeVeh} active vehicles, expected 1.")
                    # activeVeh = 0
                    continue

                receivedReports.at[cellId, 'CuCp'] = True

                Input[f'{cellId}activeVeh'] = activeVeh
                Input[f'{cellId}SINR'] = float(report.get("servingSINR", 0.0))

                for i in list(range(2, numBS+2)):
                    if i == cellId:
                        continue 
                    Input[f'{i}SINR-{cellId}'] = float(report.get(f'neighSINR{i}', 0.0)) 
                    
                cellId_imsi[cellId] = int(report.get("imsi", 0))
                if Input[f'{cellId}activeVeh'] == 1:
                    Input[f'{cellId}activeVeh'] = int(report.get("imsi"))
                
                
            elif report.get("type") == "Du":
                receivedReports.at[cellId, 'Du'] = True

                Input[f'{cellId}numTBInitial'] = int(report.get("macPduInitialCellSpecific", 0))
                Input[f'{cellId}numTBRetran'] = int(report.get("macRetxCellSpecific", 0))                                                                   
                Input[f'{cellId}numTBQPSK'] = int(report.get("macQpskCellSpecific", 0))
                Input[f'{cellId}numTB16QAM'] = int(report.get("mac16QamCellSpecific", 0))
                Input[f'{cellId}numTB64QAM'] = int(report.get("mac64QamCellSpecific", 0))


            else:
                print(f'Unknown report type: {report.get("type")}')
        else:
            print(f"Received report from unknown cellId {report.get('cellId')}")

        # print(receivedReports)
        if receivedReports.all().all():
            input = Input.values.copy()
            input = np.round(input, 2)
            inputlogger.info(f"At {round(timestamp, 2)}, Input:\n{input}")
            input = input.reshape((numBS, int(len(input)/numBS)))  # [10,17]
            RLInput.put((timestamp, input))

            receivedReports[:] = False
            Input[:] = 0
        

def RLThread ():
    global RicMsg
    try:
        os.remove(f'/home/xapp-handover_{ckpt}.log')
        os.remove('/home/xapp-handover.log')
    except FileNotFoundError:
        pass
    handoverlogger = logging.getLogger('HandoverLogger')
    # fh = logging.FileHandler(f'/home/xapp-handover_{time.strftime("%Y_%m_%d_%H_%M_%S", time.localtime())}.log')
    # fh = logging.FileHandler(f'/home/xapp-handover.log')
    fh = logging.FileHandler(f'/home/xapp-handover_{ckpt}.log', mode='w')
    fh.setFormatter(logging.Formatter('%(message)s'))
    handoverlogger.addHandler(fh)
    handoverlogger.setLevel(logging.INFO)

    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter('%(message)s'))
    handoverlogger.addHandler(sh)

    while True:
        # flag = False
        timestamp, state_np = RLInput.get()
        # print(state_np)
        # print('Mask: ', state_np[:, 0])
        if state_np[:, 0].sum() == 0:
            print(f"At {timestamp}, no active vehicles, handover decision.")

        else:
            selected_action, current_mask = select_action(agent=agent, state_np=state_np)
            if not np.array_equal(selected_action, selected_action * current_mask):
                print(f"Error: Selected action doesn't match the current mask!")
                print(f"State:\n{state_np}\nAction: {selected_action}\nMask: {current_mask}\nConnection: {state_np[:, 0]}")
                continue
            source_list, target_list = [],[]
            # print(f"Selected Action: {selected_action}")
            for i in selected_action.nonzero()[0]:
                cellId = i + 2
                if cellId == selected_action[i]:
                    continue
                # imsi = cellId_imsi.get(cellId, 0)
                # # print(f'imsi = {imsi}')
                if cellId_imsi.get(cellId, 0) != 0:
                    # RicMsg.put((imsi, selected_action[i]))
                    # handoverlogger.info(f"At {timestamp}, Veh_{imsi} handover from RSU_{cellId} to RSU_{selected_action[i]}")
                    source_list.append(cellId)
                    target_list.append(selected_action[i])
            ########## TS Msg Arrangement ##########
            i = 0
            while i < len(source_list):
                if target_list[i] not in source_list:
                    source = source_list.pop(i)
                    target = target_list.pop(i)
                    imsi = cellId_imsi.get(source, 0)
                    RicMsg.put((imsi, target))
                    handoverlogger.info(f"At {timestamp}, Veh_{imsi} handover from RSU_{source} to RSU_{target}.")
                    i = 0
                else:
                    i += 1

def deserialize_map(data: bytes) -> Dict[str, str]:
    
    result = {}
    
    if not data or len(data) < 4:
        return result
    
    offset = 0
    total_length = len(data)
    
    map_size = struct.unpack('>I', data[offset:offset+4])[0]
    # print(f"Deserializing map of size: {map_size}")
    offset += 4
    
    for _ in range(map_size):
        if offset + 4 > total_length:
            break
        
        key_len = struct.unpack('>I', data[offset:offset+4])[0]
        offset += 4
        
        if offset + key_len > total_length:
            break
        
        key = data[offset:offset+key_len].decode('utf-8')
        offset += key_len
        
        if offset + 4 > total_length:
            break
        
        val_len = struct.unpack('>I', data[offset:offset+4])[0]
        offset += 4
        
        if offset + val_len > total_length:
            break
        
        value = data[offset:offset+val_len].decode('utf-8')
        offset += val_len
        
        result[key] = value
        # print(f"Deserialized key-value pair: {key} -> {value}")
    
    return result
