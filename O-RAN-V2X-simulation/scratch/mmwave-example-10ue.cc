/* -*-  Mode: C++; c-file-style: "gnu"; indent-tabs-mode:nil; -*- */
/*
*   Copyright (c) 2011 Centre Tecnologic de Telecomunicacions de Catalunya (CTTC)
*   Copyright (c) 2015, NYU WIRELESS, Tandon School of Engineering, New York University
*
*   This program is free software; you can redistribute it and/or modify
*   it under the terms of the GNU General Public License version 2 as
*   published by the Free Software Foundation;
*
*   This program is distributed in the hope that it will be useful,
*   but WITHOUT ANY WARRANTY; without even the implied warranty of
*   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
*   GNU General Public License for more details.
*
*   You should have received a copy of the GNU General Public License
*   along with this program; if not, write to the Free Software
*   Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
*
*   Author: Marco Miozzo <marco.miozzo@cttc.es>
*           Nicola Baldo  <nbaldo@cttc.es>
*
*   Modified by: Marco Mezzavilla < mezzavilla@nyu.edu>
*                         Sourjya Dutta <sdutta@nyu.edu>
*                         Russell Ford <russell.ford@nyu.edu>
*                         Menglei Zhang <menglei@nyu.edu>
*/


#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/mobility-module.h"
#include "ns3/config-store.h"
#include "ns3/mmwave-helper.h"
#include <ns3/buildings-helper.h>
#include "ns3/global-route-manager.h"
#include "ns3/ipv4-global-routing-helper.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"
#include "ns3/log.h"
#include "ns3/node-container.h"
#include "ns3/mmwave-propagation-loss-model.h"
#include "ns3/mmwave-enb-phy.h"
#include "ns3/mmwave-enb-net-device.h"
#include "ns3/mmwave-ue-net-device.h"

using namespace ns3;
using namespace mmwave;

int
main (int argc, char *argv[])
{
  CommandLine cmd;
  cmd.Parse (argc, argv);

  /* Information regarding the traces generated:
   *
   * 1. UE_1_SINR.txt : Gives the SINR for each sub-band
   *    Subframe no.  | Slot No. | Sub-band  | SINR (db)
   *
   * 2. UE_1_Tb_size.txt : Allocated transport block size
   *    Time (micro-sec)  |  Tb-size in bytes
   * */

  Ptr<MmWaveHelper> ptr_mmWave = CreateObject<MmWaveHelper> ();
  /* A configuration example.
   * ptr_mmWave->GetCcPhyParams ().at (0).GetConfigurationParameters ()->SetAttribute("SymbolPerSlot", UintegerValue(30)); */

  //set line of sight loss propagation model
  Config::SetDefault ("ns3::MmWavePropagationLossModel::ChannelStates", StringValue ("l")); //LoS
  //Config::SetDefault ("ns3::MmWavePropagationLossModel::FixedLossTst", BooleanValue (true)); //enable fixed loss
  //Config::SetDefault ("ns3::MmWavePropagationLossModel::LossFixedDb", DoubleValue (165.0)); //fixed loss value

  //set transmitting power
  Config::SetDefault ("ns3::MmWaveEnbPhy::TxPower", DoubleValue (30.0));
  Config::SetDefault ("ns3::MmWaveUePhy::TxPower", DoubleValue (30.0));

 //ptr_mmWave->SetPathlossModelType("ns3::MmWavePropagationLossModel");
  ptr_mmWave->SetChannelConditionModelType("ns3::AlwaysLosChannelConditionModel");

  //set enb and ue antenna number
  // ptr_mmWave->SetMmWaveEnbNetDeviceAttribute("AntennaNum", UintegerValue (4));
  // ptr_mmWave->SetMmWaveUeNetDeviceAttribute("AntennaNum", UintegerValue (1));

  //configure centerfreq and channel bandwidth
 
  double ChannelBandwidth = 100e6;

  uint8_t numCc = 1; // number of CCs
  double freq[] {28.0e9}; // frequency of the CCs
  
  // create the MmWaveHelper
  ptr_mmWave->SetAttribute ("UseCa", BooleanValue ((numCc > 1)));
  ptr_mmWave->SetAttribute ("NumberOfComponentCarriers", UintegerValue (numCc));

  // create and configure the CCs
  std::map<uint8_t, MmWaveComponentCarrier> ccMap;
  for (uint8_t i = 0; i < numCc; i++)
  {
    Ptr<MmWavePhyMacCommon> phyMacConfig = CreateObject<MmWavePhyMacCommon> ();
    phyMacConfig->SetAttribute ("CenterFreq", DoubleValue (freq [i]));

    phyMacConfig->SetBandwidth (ChannelBandwidth);

    Ptr<MmWaveComponentCarrier> cc = CreateObject<MmWaveComponentCarrier> ();
    cc->SetConfigurationParameters (phyMacConfig);
    cc->SetAsPrimary ((i == 0));
    ccMap [i] = *cc;
  }
  
  ptr_mmWave->SetCcPhyParams (ccMap);
  
  
  //define number of UEs
  uint16_t numUe = 10;

  NodeContainer enbNodes;
  NodeContainer ueNodes;
  enbNodes.Create (1);
  ueNodes.Create (numUe);

  Ptr<ListPositionAllocator> enbPositionAlloc = CreateObject<ListPositionAllocator> ();
  enbPositionAlloc->Add (Vector (0.0, 0.0, 0.0));

  MobilityHelper enbmobility;
  enbmobility.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  enbmobility.SetPositionAllocator (enbPositionAlloc);
  enbmobility.Install (enbNodes);
  BuildingsHelper::Install (enbNodes);

  MobilityHelper uemobility;
  Ptr<ListPositionAllocator> uePositionAlloc = CreateObject<ListPositionAllocator> ();
  //uePositionAlloc->Add (Vector (100.0, 0.0, 0.0));//single ue position


  //generate location for UEs
  Ptr<UniformRandomVariable> distRv = CreateObject<UniformRandomVariable> ();

  for (unsigned i = 0; i < numUe; i++)
    {
      double dist = distRv->GetValue (90.0, 100.0);
      uePositionAlloc->Add (Vector (dist, 0.0, 0.0));
    }

  uemobility.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  uemobility.SetPositionAllocator (uePositionAlloc);
  uemobility.Install (ueNodes);
  BuildingsHelper::Install (ueNodes);

  NetDeviceContainer enbNetDev = ptr_mmWave->InstallEnbDevice (enbNodes);
  NetDeviceContainer ueNetDev = ptr_mmWave->InstallUeDevice (ueNodes);

  ptr_mmWave->AttachToClosestEnb (ueNetDev, enbNetDev);
  ptr_mmWave->EnableTraces ();

  // Activate a data radio bearer
  enum EpsBearer::Qci q = EpsBearer::GBR_CONV_VOICE;

  EpsBearer bearer (q);
  ptr_mmWave->ActivateDataRadioBearer (ueNetDev, bearer);

  // //get the loss model for the default CC
  // Ptr<MmWavePropagationLossModel> lossModel = ptr_mmWave->GetPathLossModel (0)->GetObject<ThreeGppPropgationLossModel>();
  // NS_LOG_UNCOND ("lossModel" << lossModel);

  Simulator::Stop (Seconds (0.5));
  Simulator::Run ();
  Simulator::Destroy ();
  return 0;
}

