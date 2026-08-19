import numpy as np
import queue as q
from xapp_control import *
import os

np.set_printoptions(precision=3, suppress=True)

numUE = 8
numBS = -1
with open("../xapp-sm-connector/init/rsu_list.txt", 'r') as f:
    for line in f:
        numBS += 1
SINRMatrix = np.zeros((numUE, 2 * 4))
targetBS = [1 for i in range(numUE)]
outageSINR = 0.0    # -10.0
RicMsg = q.Queue(-1)

try:
    os.remove('/home/xapp-handover.log')
except FileNotFoundError:
    pass
try:
    os.remove('/home/xapp-connection.log')
except FileNotFoundError:
    pass
handoverlogger = logging.getLogger('HandoverLogger')
fh = logging.FileHandler('/home/xapp-handover.log')
fh.setFormatter(logging.Formatter('%(message)s'))
handoverlogger.addHandler(fh)
handoverlogger.setLevel(logging.INFO)
connectionlogger = logging.getLogger('ConnectionLogger')
fh2 = logging.FileHandler('/home/xapp-connection.log')
fh2.setFormatter(logging.Formatter('%(message)s'))
connectionlogger.addHandler(fh2)
connectionlogger.setLevel(logging.INFO)

def thresholdHandover (timestamp, cBS, threshold = 0.0):
    # print(f"HO strategy is THRESHOLD_BASED, Threshold = {threshold} dB")
    targetBS = [1 for i in range(numUE)]
    imsiHandover = []
    for ue in range(numUE):

        if SINRMatrix[ue][1] <= outageSINR and ((SINRMatrix[ue][3] <=outageSINR or int(SINRMatrix[ue][2]) in cBS) and (SINRMatrix[ue][5] <=outageSINR or int(SINRMatrix[ue][4]) in cBS)): # and (SINRMatrix[ue][7] <=outageSINR or int(SINRMatrix[ue][6]) in cBS):
            targetBS[ue] = 1  # No BS available
        else:
            if cBS[ue] != 1:
                if cBS[ue] != SINRMatrix[ue][0]:
                    continue
                if (SINRMatrix[ue][3] - SINRMatrix[ue][1] > threshold or (SINRMatrix[ue][1] <= outageSINR and SINRMatrix[ue][3] > outageSINR)) and int(SINRMatrix[ue][2]) not in cBS:
                    targetBS[ue] = int(SINRMatrix[ue][2])
                    # print(f"11")
                    t_sinr = SINRMatrix[ue][3]
                elif (SINRMatrix[ue][5] - SINRMatrix[ue][1] > threshold or (SINRMatrix[ue][1] <= outageSINR and SINRMatrix[ue][5] > outageSINR)) and int(SINRMatrix[ue][4]) not in cBS:
                    targetBS[ue] = int(SINRMatrix[ue][4])
                    # print(f'22')
                    t_sinr = SINRMatrix[ue][5]
                # elif (SINRMatrix[ue][7] - SINRMatrix[ue][1] > threshold or (SINRMatrix[ue][1] <= outageSINR and SINRMatrix[ue][7] > outageSINR)) and int(SINRMatrix[ue][6]) not in cBS:
                #     targetBS[ue] = int(SINRMatrix[ue][6])
                #    t_sinr = SINRMatrix[ue][7]
                else:                 
                    targetBS[ue] = int(SINRMatrix[ue, 0])    # Keep the current connection
                    t_sinr = SINRMatrix[ue][1]
                    # continue
            else:
                if (SINRMatrix[ue][1] > outageSINR) and SINRMatrix[ue][0] not in cBS:
                    targetBS[ue] = int(SINRMatrix[ue][0])
                    t_sinr = SINRMatrix[ue][1]
                elif (SINRMatrix[ue][3] > outageSINR) and SINRMatrix[ue][2] not in cBS:
                    targetBS[ue] = int(SINRMatrix[ue][2])
                    t_sinr = SINRMatrix[ue][3]
                elif (SINRMatrix[ue][5] > outageSINR) and SINRMatrix[ue][4] not in cBS:
                    targetBS[ue] = int(SINRMatrix[ue][4])
                    t_sinr = SINRMatrix[ue][5]
                # elif (SINRMatrix[ue][7] > outageSINR) and SINRMatrix[ue][6] not in cBS:
                #     targetBS[ue] = int(SINRMatrix[ue][6])
                #     t_sinr = SINRMatrix[ue][7]
                else:
                    targetBS[ue] = int(SINRMatrix[ue, 0])    # Keep the current connection
                    t_sinr = SINRMatrix[ue][1]
                    # continue
        imsiHandover.append(ue+1)
            
    print(f"targetBS after HO: {targetBS}\nconnectedBS before HO: {cBS}")   #\nimsiHandover: {imsiHandover}")
    # return imsiHandover, targetBS
    for i in imsiHandover:
        
        if targetBS[i-1] == 1:
            if cBS[i-1] != 1:
                handoverlogger.info(f"At {timestamp}, UE{i} disconnected from the network")
            cBS[i-1] = 1
        else:
            print(f"UE{i}: current gNB{cBS[i-1]}, target gNB{targetBS[i-1]}")
            if cBS[i-1] != targetBS[i-1]:
                # print(f"1")
                if targetBS[i-1] not in cBS:
                    # print(f"2")
                    if cBS[i-1] != 1:
                        handoverlogger.info(f"At {timestamp}, UE{i} handover from gNB{cBS[i-1]} to gNB{targetBS[i-1]}")
                        RicMsg.put((int(i), int(targetBS[i-1])))
                        # print(f'1_UE{i} sinrMatrix:\n{SINRMatrix[i-1]}')
                        SINRMatrix[i-1][0], SINRMatrix[i-1][1] = targetBS[i-1], t_sinr
                    else:
                        handoverlogger.info(f"At {timestamp}, UE{i} (re)connect to the gNB{targetBS[i-1]}")
                        if targetBS[i-1] != int(SINRMatrix[i-1][0]):
                            RicMsg.put((int(i), int(targetBS[i-1])))
                            # print(f'2_UE{i} sinrMatrix:\n{SINRMatrix[i-1]}')
                            SINRMatrix[i-1][0], SINRMatrix[i-1][1] = targetBS[i-1], t_sinr
                            # print(f"4")
                    
                    cBS[i-1] = targetBS[i-1]
            else:
                # print(f"3")
                continue    # No HO needed
    return cBS

def TttHandover (timestamp, cBS, waitHO={}, threshold = 0.0, ttt = 3):
    # ttt /= 1000
    # print(f"HO strategy is FIXEDTTT_BASED, Ttt= {ttt} s, Threshold = {threshold} dB")
    targetBS = [1 for i in range(numUE)]
    imsiHandover = []

    for ue in range(numUE):

        if SINRMatrix[ue][1] <= outageSINR and ((SINRMatrix[ue][3] <=outageSINR or int(SINRMatrix[ue][2]) in cBS) and (SINRMatrix[ue][5] <=outageSINR or int(SINRMatrix[ue][4]) in cBS)): # and (SINRMatrix[ue][7] <=outageSINR or int(SINRMatrix[ue][6]) in cBS):
            targetBS[ue] = 1  # No BS available
        else:
            if SINRMatrix[ue][3] - SINRMatrix[ue][1] > threshold or (SINRMatrix[ue][1] <= outageSINR and SINRMatrix[ue][3] > outageSINR and int(SINRMatrix[ue][2]) not in cBS):
                targetBS[ue] = int(SINRMatrix[ue][2])
                # t_sinr = SINRMatrix[ue][3]
            elif SINRMatrix[ue][5] - SINRMatrix[ue][1] > threshold or (SINRMatrix[ue][1] <= outageSINR and SINRMatrix[ue][5] > outageSINR and int(SINRMatrix[ue][4]) not in cBS):
                targetBS[ue] = int(SINRMatrix[ue][4])
                # t_sinr = SINRMatrix[ue][5]
            # elif SINRMatrix[ue][7] - SINRMatrix[ue][1] > threshold or (SINRMatrix[ue][1] <= outageSINR and SINRMatrix[ue][7] > outageSINR and int(SINRMatrix[ue][6]) not in cBS):
            #     targetBS[ue] = int(SINRMatrix[ue][6])
            #    # t_sinr = SINRMatrix[ue][7]
            else:                 
                targetBS[ue] = int(SINRMatrix[ue, 0])    # Keep the current connection
        imsiHandover.append(ue+1)

    for i in imsiHandover:
        if targetBS[i-1] == 1:
            if cBS[i-1] != 1:
                handoverlogger.info(f"At {timestamp}, UE{i} disconnected from the network")
            cBS[i-1] = 1
        else:
            if cBS[i-1] != targetBS[i-1]:
                print(f"1")
                if targetBS[i-1] not in cBS:
                    print(f"2")
                    if cBS[i-1] != 1:
                        print(f'waitHO before adding new event: {waitHO}')
                        if waitHO.__len__() > 0 and f'{i}' in waitHO:
                            print(f"UE{i} already in waitHO list, skip adding new HO event")
                            continue
                        print(f'Event: {float(timestamp) + ttt}, {int(i)}, {int(targetBS[i-1])}')
                        waitHO[f"{i}"] = [float(timestamp) + ttt, int(targetBS[i-1])]   # imsi: [startTime, targetBS]
                    else:
                        handoverlogger.info(f"At {timestamp}, UE{i} (re)connect to the gNB{targetBS[i-1]}")
                        if targetBS[i-1] != int(SINRMatrix[i-1][0]):
                            RicMsg.put((int(i), int(targetBS[i-1])))
                            # SINRMatrix[i-1][0], SINRMatrix[i-1][1] = targetBS[i-1], t_sinr
                            print(f"4")
                        cBS[i-1] = targetBS[i-1]  # Update cBS only when the HO is executed
            else:
                print(f"3")
                continue    # No HO needed
    # Check if any HO can be executed
    while waitHO.__len__() > 0:
        waitList = list(waitHO.values())
        if waitList[0][0] > float(timestamp):
            break
        imsi = int(list(waitList.keys())[0])
        target = int(waitHO.pop(imsi)[1])
        if target == SINRMatrix[imsi-1][0]:
            print(f"UE {imsi} already connected to gNB{target}, remove the HO event")
            continue

        if SINRMatrix[imsi-1][2] == target and SINRMatrix[imsi-1][3] - SINRMatrix[imsi-1][1] > threshold:
            handoverlogger.info(f"At {timestamp}, UE{imsi} handover from gNB{cBS[imsi-1]} to gNB{target}")
            RicMsg.put((int(imsi), int(target)))
            cBS[imsi-1] = target
        # else:
        #     print(f"UE {imsi} has already executed HO to gNB{target}, remove the HO event")


    return cBS, waitHO
