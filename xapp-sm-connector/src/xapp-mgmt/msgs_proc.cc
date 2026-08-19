/*
==================================================================================

        Copyright (c) 2019-2020 AT&T Intellectual Property.

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
==================================================================================
*/
/*
 * msgs_proc.cc
 * Created on: 2019
 * Author: Ashwin Shridharan, Shraboni Jana
 */


#include "msgs_proc.hpp"
#include <stdio.h>
#include <map>


bool XappMsgHandler::encode_subscription_delete_request(unsigned char* buffer, size_t *buf_len){

	subscription_helper sub_helper;
	sub_helper.set_request(0); // requirement of subscription manager ... ?
	sub_helper.set_function_id(0);

	subscription_delete e2ap_sub_req_del;

	  // generate the delete request pdu

	  bool res = e2ap_sub_req_del.encode_e2ap_subscription(&buffer[0], buf_len, sub_helper);
	  if(! res){
	    mdclog_write(MDCLOG_ERR, "%s, %d: Error encoding subscription delete request pdu. Reason = %s", __FILE__, __LINE__, e2ap_sub_req_del.get_error().c_str());
	    return false;
	  }

	return true;

}

bool XappMsgHandler::decode_subscription_response(unsigned char* data_buf, size_t data_size){

	subscription_helper subhelper;
	subscription_response subresponse;
	bool res = true;
	E2AP_PDU_t *e2pdu = 0;

	asn_dec_rval_t rval;

	ASN_STRUCT_RESET(asn_DEF_E2AP_PDU, e2pdu);

	rval = asn_decode(0,ATS_ALIGNED_BASIC_PER, &asn_DEF_E2AP_PDU, (void**)&e2pdu, data_buf, data_size);
	switch(rval.code)
	{
		case RC_OK:
			   //Put in Subscription Response Object.
			   //asn_fprint(stdout, &asn_DEF_E2AP_PDU, e2pdu);
			   break;
		case RC_WMORE:
				mdclog_write(MDCLOG_ERR, "RC_WMORE");
				res = false;
				break;
		case RC_FAIL:
				mdclog_write(MDCLOG_ERR, "RC_FAIL");
				res = false;
				break;
		default:
				break;
	 }
	ASN_STRUCT_FREE(asn_DEF_E2AP_PDU, e2pdu);
	return res;

}

bool  XappMsgHandler::a1_policy_handler(char * message, int *message_len, a1_policy_helper &helper){

  rapidjson::Document doc;
  if (doc.Parse(message).HasParseError()){
    mdclog_write(MDCLOG_ERR, "Error: %s, %d :: Could not decode A1 JSON message %s\n", __FILE__, __LINE__, message);
    return false;
  }

  //Extract Operation
  rapidjson::Pointer temp1("/operation");
    rapidjson::Value * ref1 = temp1.Get(doc);
    if (ref1 == NULL){
      mdclog_write(MDCLOG_ERR, "Error : %s, %d:: Could not extract policy type id from %s\n", __FILE__, __LINE__, message);
      return false;
    }

   helper.operation = ref1->GetString();

  // Extract policy id type
  rapidjson::Pointer temp2("/policy_type_id");
  rapidjson::Value * ref2 = temp2.Get(doc);
  if (ref2 == NULL){
    mdclog_write(MDCLOG_ERR, "Error : %s, %d:: Could not extract policy type id from %s\n", __FILE__, __LINE__, message);
    return false;
  }
   //helper.policy_type_id = ref2->GetString();
    helper.policy_type_id = to_string(ref2->GetInt());

    // Extract policy instance id
    rapidjson::Pointer temp("/policy_instance_id");
    rapidjson::Value * ref = temp.Get(doc);
    if (ref == NULL){
      mdclog_write(MDCLOG_ERR, "Error : %s, %d:: Could not extract policy type id from %s\n", __FILE__, __LINE__, message);
      return false;
    }
    helper.policy_instance_id = ref->GetString();

    if (helper.policy_type_id == "1" && helper.operation == "CREATE"){
    	helper.status = "OK";
    	Document::AllocatorType& alloc = doc.GetAllocator();

    	Value handler_id;
    	handler_id.SetString(helper.handler_id.c_str(), helper.handler_id.length(), alloc);

    	Value status;
    	status.SetString(helper.status.c_str(), helper.status.length(), alloc);


    	doc.AddMember("handler_id", handler_id, alloc);
    	doc.AddMember("status",status, alloc);
    	doc.RemoveMember("operation");
    	StringBuffer buffer;
    	Writer<StringBuffer> writer(buffer);
    	doc.Accept(writer);
    	strncpy(message,buffer.GetString(), buffer.GetLength());
    	*message_len = buffer.GetLength();
    	return true;
    }
    return false;
 }


//For processing received messages.XappMsgHandler should mention if resend is required or not.
void XappMsgHandler::operator()(rmr_mbuf_t *message, bool *resend){

	if (message->len > MAX_RMR_RECV_SIZE){
		mdclog_write(MDCLOG_ERR, "Error : %s, %d, RMR message larger than %d. Ignoring ...", __FILE__, __LINE__, MAX_RMR_RECV_SIZE);
		return;
	}
	a1_policy_helper helper;
	bool res=false;
	switch(message->mtype){
		//need to fix the health check.
		case (RIC_HEALTH_CHECK_REQ):
				message->mtype = RIC_HEALTH_CHECK_RESP;        // if we're here we are running and all is ok
				message->sub_id = -1;
				strncpy( (char*)message->payload, "HELLOWORLD OK\n", rmr_payload_size( message) );
				*resend = true;
				break;

		case (RIC_INDICATION): {

			mdclog_write(MDCLOG_INFO, "Received RIC indication message of type = %d", message->mtype);

			unsigned char *me_id_null;
			unsigned char *me_id = rmr_get_meid(message, me_id_null);
			mdclog_write(MDCLOG_INFO,"RMR Received MEID: %s",me_id);

			process_ric_indication(message->mtype, me_id, message->payload, message->len);

			break;
		}

		case (RIC_SUB_RESP): {
        		mdclog_write(MDCLOG_INFO, "Received subscription message of type = %d", message->mtype);

				unsigned char *me_id_null;
				unsigned char *me_id = rmr_get_meid(message, me_id_null);
				mdclog_write(MDCLOG_INFO,"RMR Received MEID: %s",me_id);

				if(_ref_sub_handler !=NULL){
					_ref_sub_handler->manage_subscription_response(message->mtype, me_id, message->payload, message->len);
				} else {
					mdclog_write(MDCLOG_ERR, " Error :: %s, %d : Subscription handler not assigned in message processor !", __FILE__, __LINE__);
				}
				*resend = false;
				break;
		 }

		case A1_POLICY_REQ:
		{
		    mdclog_write(MDCLOG_INFO, "In Message Handler: Received A1_POLICY_REQ.");
			helper.handler_id = xapp_id;

			res = a1_policy_handler((char*)message->payload, &message->len, helper);
			if(res){
				message->mtype = A1_POLICY_RESP;        // if we're here we are running and all is ok
				message->sub_id = -1;
				*resend = true;
			}
			break;
		}
		default:
		{
			mdclog_write(MDCLOG_ERR, "Error :: Unknown message type %d received from RMR", message->mtype);
			*resend = false;
		}
	}

	return;

};

void process_ric_indication(int message_type, transaction_identifier id, const void *message_payload, size_t message_len) {

	std::cout << "In Process RIC indication" << std::endl;
	
	std::cout << "ID " << id << std::endl;

	// decode received message payload
  E2AP_PDU_t *pdu = nullptr;
  auto retval = asn_decode(nullptr, ATS_ALIGNED_BASIC_PER, &asn_DEF_E2AP_PDU, (void **) &pdu, message_payload, message_len);

  // print decoded payload
  if (retval.code == RC_OK) {
    char *printBuffer;
    size_t size;
    FILE *stream = open_memstream(&printBuffer, &size);
    asn_fprint(stream, &asn_DEF_E2AP_PDU, pdu);
    mdclog_write(MDCLOG_DEBUG, "Decoded E2AP PDU: %s", printBuffer);

    uint8_t res = procRicIndication(pdu, id);
  }
	else {
		std::cout << "process_ric_indication, retval.code " << retval.code << std::endl;
	}
}

/**
 * Handle RIC indication
 * TODO doxy
 */
uint8_t procRicIndication(E2AP_PDU_t *e2apMsg, transaction_identifier gnb_id)
{
   uint8_t idx;
   uint8_t ied;
   uint8_t ret = RC_OK;
   uint32_t recvBufLen;
   RICindication_t *ricIndication;
   RICaction_ToBeSetup_ItemIEs_t *actionItem;

   printf("\nE2AP : RIC Indication received");
   ricIndication = &e2apMsg->choice.initiatingMessage->value.choice.RICindication;

//    printf("\nprotocolIEs elements %d\n", ricIndication->protocolIEs.list.count);

   for (idx = 0; idx < ricIndication->protocolIEs.list.count; idx++)
   {
      switch(ricIndication->protocolIEs.list.array[idx]->id)
      {
		case 28:  // RIC indication type
		{
			long ricindicationType = ricIndication->protocolIEs.list.array[idx]-> \
																	value.choice.RICindicationType;

			// printf("ricindicationType %ld\n", ricindicationType);

			break;
		}
		case 26:  // RIC indication message
		{
			size_t payload_size = ricIndication->protocolIEs.list.array[idx]-> \
																	value.choice.RICindicationMessage.size;


			char* payload = (char*) calloc(payload_size, sizeof(char));
			memcpy(payload, ricIndication->protocolIEs.list.array[idx]-> \
																	value.choice.RICindicationMessage.buf, payload_size);
			
			std::string agent_ip = find_agent_ip_from_gnb(gnb_id);
			// std::cout << gnb_id << " agent_ip: " << agent_ip << " payload: " << payload << "\n" << std::endl;
			// map<string, string> decodePayload = DecodeIndicationMessage(payload,payload_size);
			// DecodeIndicationMessage(payload,payload_size);
			std::map<std::string, std::string> report = deserialize_map((uint8_t*)payload, payload_size);
			for (const auto& [key, value] : report) {
        		std::cout << key << ": " << value << std::endl;
    		}
			std::lock_guard<std::mutex> lock(socket_send_mutex);
			send_socket(payload, payload_size, agent_ip);
			free(payload);
			break;
		}
      }
   }
   return ret; // TODO update ret value in case of errors
}

// map<string, string>
// readPfDuContainer (ODU_PF_Container_t *oDU)
// {
//   map<string, string> duReport;
//     int count = oDU->cellResourceReportList.list.count;
//   if (count <= 0) {
// 	std::cout << "[E2SM] received empty ODU list" << std::endl;
//   }
//   else {
// 	for (int i = 0; i < count; i++)
// 	{
// 		CellResourceReportListItem_t *report = oDU->cellResourceReportList.list.array[i];
		
// 		std::cout << "CellResourceReportListItem " << i << "Buf PlmNID: " << report->nRCGI.pLMN_Identity.buf << std::endl;
		
// 		uint64_t cellId = 0;
// 		for (int j = 0; j < sizeof(report->nRCGI.nRCellIdentity.buf); j++){
// 		if (report->nRCGI.nRCellIdentity.buf[j] == 0x00){
// 			break;
// 		}
// 		cellId = cellId * 10 + (report->nRCGI.nRCellIdentity.buf[j] - 0x30);
// 		}
// 		cellId = cellId >> report->nRCGI.nRCellIdentity.bits_unused;
// 		std::cout << "CellId: " << cellId << std::endl;
// 		long ulTotalOfAvailablePRBs = *(report->ul_TotalofAvailablePRBs);
// 		long dlTotalOfAvailablePRBs = *(report->dl_TotalofAvailablePRBs);
// 		std::cout << "UL Total of Available PRBs: " << ulTotalOfAvailablePRBs << std::endl;
// 		std::cout << "DL Total of Available PRBs: " << dlTotalOfAvailablePRBs << std::endl;

// 		for (int j = 0; j < report->servedPlmnPerCellList.list.count; j++)
// 		{
// 		ServedPlmnPerCellListItem_t *servedPlmnPerCell = report->servedPlmnPerCellList.list.array[j];      
// 		FGC_DU_PM_Container_t* fgcDuPmContainer = servedPlmnPerCell->du_PM_5GC;
// 		if (fgcDuPmContainer != NULL)
// 		{
// 			// NS_LOG_UNCOND ("5GC DU PM Container");
// 			// NS_LOG_UNCOND (xer_fprint (stderr, &asn_DEF_FGC_DU_PM_Container, fgcDuPmContainer));
// 		}

// 		EPC_DU_PM_Container_t *epcDuPmContainer = servedPlmnPerCell->du_PM_EPC;
// 		if(epcDuPmContainer != NULL)
// 		{
// 			for (int z = 0; z < epcDuPmContainer->perQCIReportList_du.list.count; z++)
// 			{
// 				PerQCIReportListItem_t * perQCIReportItem = epcDuPmContainer->perQCIReportList_du.list.array[z];
// 				long dlPrbUsage = *perQCIReportItem->dl_PRBUsage;
// 				long ulPrbUsage = *perQCIReportItem->ul_PRBUsage;
// 				long qci =  perQCIReportItem->qci;
// 				std::cout << "QCI " << qci << ", dlPrbUsage: " << dlPrbUsage << ", ulPrbUsage: " << ulPrbUsage << std::endl;
// 			}
// 		}
// 		}
//   }}
//   return duReport;
// }

// map<string, string>
// readPfCuContainer (OCUCP_PF_Container_t *oCU_CP)
// {
//   long numActiveUes = *oCU_CP->cu_CP_Resource_Status.numberOfActive_UEs;
//   std::cout << "OCUCP_PF_Container_t " << "Number of Active UEs: " << numActiveUes << std::endl;
// 	map<string, string> cuCpReport;
// 	cuCpReport["KPM"] = "CU_CP";
// 	cuCpReport["Number of Active UEs"] = std::to_string(numActiveUes);
// 	return cuCpReport;
// }

// map<string, string>
// readPfCuContainer (OCUUP_PF_Container_t *oCU_UP)
// {
// 	std::cout << "OCUUP_PF_Container_t" << std::endl;
// 	map<string, string> cuUpReport;
// 	cuUpReport["KPM"] = "CU_UP";
// 	return cuUpReport;
// }

// map<string, string>
// ProcessIndicationMessage (E2SM_KPM_IndicationMessage_t *indMsg)
// {
//   if (indMsg->present == E2SM_KPM_IndicationMessage_PR_indicationMessage_Format1)
//   {
//     E2SM_KPM_IndicationMessage_Format1_t *e2SmIndicationMessageFormat1 = indMsg->choice.indicationMessage_Format1;

//     // extract RAN container, which is where we put our payload
//     std::vector<uint8_t *> serving_cell_payload_vec;
//     std::vector<uint8_t *> neighbor_cell_payload_vec;
//     for (int i = 0; i < e2SmIndicationMessageFormat1->pm_Containers.list.count; i++){
//       PM_Containers_Item_t *pmContainer = e2SmIndicationMessageFormat1->pm_Containers.list.array[i];
//       PF_Container_t *pfContainer = pmContainer->performanceContainer;
//       switch (pfContainer->present)
//         {
//         case PF_Container_PR_NOTHING:
//           break;

//         case PF_Container_PR_oDU:
//           return readPfDuContainer (pfContainer->choice.oDU);

//         case PF_Container_PR_oCU_CP:
//           return readPfCuContainer (pfContainer->choice.oCU_CP);

//         case PF_Container_PR_oCU_UP:
//           return readPfCuContainer (pfContainer->choice.oCU_UP);

//         default:
//           break;
//         }
//     }
//   }
//   else
//   {
//     std::cout << "No payload received in RIC Indication message (or was unable to decode received payload\n" << std::endl;
//   }
// }

// map<string, string>
// DecodeIndicationMessage (char *msg, size_t msg_len)
// {
//   asn_dec_rval_t decode_result;
//   E2SM_KPM_IndicationMessage_t *indMsg = 0;

//   decode_result = aper_decode_complete (NULL, &asn_DEF_E2SM_KPM_IndicationMessage,
//                                         (void **) &indMsg, msg, msg_len);

//   if (decode_result.code == RC_OK)
//     {   
//       return ProcessIndicationMessage (indMsg);
//     }
//   else
//     {
//       ASN_STRUCT_FREE (asn_DEF_E2SM_KPM_IndicationMessage, indMsg);
//     }
// }

std::map<std::string, std::string> deserialize_map(uint8_t* arrayPtr, size_t arrayLength) {
    std::map<std::string, std::string> result;
    
    if (arrayPtr == nullptr || arrayLength < sizeof(uint32_t)) {
        return result; 
    }
    
    size_t offset = 0;
    const uint8_t* data = arrayPtr;
    
    uint32_t mapSize;
    std::memcpy(&mapSize, data + offset, sizeof(uint32_t));
    offset += sizeof(uint32_t);
    mapSize = ntohl(mapSize);
    
    for (uint32_t i = 0; i < mapSize; i++) {
        if (offset + sizeof(uint32_t) > arrayLength) {
            break; 
        }
        
        uint32_t keyLen;
        std::memcpy(&keyLen, data + offset, sizeof(uint32_t));
        offset += sizeof(uint32_t);
        keyLen = ntohl(keyLen);
        
        if (offset + keyLen > arrayLength) {
            break;
        }
        
        std::string key(reinterpret_cast<const char*>(data + offset), keyLen);
        offset += keyLen;
        
        if (offset + sizeof(uint32_t) > arrayLength) {
            break;
        }
        
        uint32_t valLen;
        std::memcpy(&valLen, data + offset, sizeof(uint32_t));
        offset += sizeof(uint32_t);
        valLen = ntohl(valLen);
        
        if (offset + valLen > arrayLength) {
            break; 
        }
        
        std::string value(reinterpret_cast<const char*>(data + offset), valLen);
        offset += valLen;
        
        result[key] = value;
    }
    
    return result;
}