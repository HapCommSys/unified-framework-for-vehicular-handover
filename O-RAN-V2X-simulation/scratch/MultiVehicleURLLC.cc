#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/applications-module.h"
#include "ns3/point-to-point-helper.h"
#include <ns3/lte-ue-net-device.h>
#include "ns3/mmwave-helper.h"
#include "ns3/epc-helper.h"
#include "ns3/mmwave-point-to-point-epc-helper.h"
#include "ns3/lte-helper.h"
#include <iostream>
#include <fstream>
#include <sstream>
#include "ns3/mobility-module.h"
#include "ns3/ns2-mobility-helper.h"
#include "ns3/flow-monitor-helper.h"
#include "ns3/config-store-module.h"

using namespace ns3;
using namespace mmwave;

// // Prints actual position and velocity when a course change event occurs
// static void CourseChange (std::ostream *os, std::string foo, Ptr<const MobilityModel> mobility)
// {
//   Vector pos = mobility->GetPosition (); // Get position
//   Vector vel = mobility->GetVelocity (); // Get velocity

//   // Prints position and velocities
//   *os << Simulator::Now () << " POS: x=" << pos.x << ", y=" << pos.y
//       << ", z=" << pos.z << "; VEL:" << vel.x << ", y=" << vel.y
//       << ", z=" << vel.z << std::endl;
// }

NS_LOG_COMPONENT_DEFINE ("MultiVehicleURLLC");

static ns3::GlobalValue g_bufferSize ("bufferSize", "RLC tx buffer size (MB)",
                                      ns3::UintegerValue (10),
                                      ns3::MakeUintegerChecker<uint32_t> ());

static ns3::GlobalValue g_enableTraces ("enableTraces", "If true, generate ns-3 traces",
                                        ns3::BooleanValue (true), ns3::MakeBooleanChecker ());

static ns3::GlobalValue g_e2lteEnabled ("e2lteEnabled", "If true, send LTE E2 reports",
                                        ns3::BooleanValue (true), ns3::MakeBooleanChecker ());

static ns3::GlobalValue g_e2nrEnabled ("e2nrEnabled", "If true, send NR E2 reports",
                                       ns3::BooleanValue (true), ns3::MakeBooleanChecker ());

static ns3::GlobalValue g_e2du ("e2du", "If true, send DU reports", ns3::BooleanValue (true),
                                ns3::MakeBooleanChecker ());

static ns3::GlobalValue g_e2cuUp ("e2cuUp", "If true, send CU-UP reports", ns3::BooleanValue (true),
                                  ns3::MakeBooleanChecker ());

static ns3::GlobalValue g_e2cuCp ("e2cuCp", "If true, send CU-CP reports", ns3::BooleanValue (true),
                                  ns3::MakeBooleanChecker ());

static ns3::GlobalValue g_reducedPmValues ("reducedPmValues", "If true, use a subset of the the pm containers",
                                        ns3::BooleanValue (true), ns3::MakeBooleanChecker ());

static ns3::GlobalValue
    g_hoSinrDifference ("hoSinrDifference",
                        "The value for which an oggginghandover between MmWave eNB is triggered",
                        ns3::DoubleValue (3), ns3::MakeDoubleChecker<double> ());

static ns3::GlobalValue
    g_indicationPeriodicity ("indicationPeriodicity",
                             "E2 Indication Periodicity reports (value in seconds)",
                             ns3::DoubleValue (0.1), ns3::MakeDoubleChecker<double> (0.01, 2.0));

// static ns3::GlobalValue g_simTime ("simTime", "Simulation time in seconds", ns3::DoubleValue (2),
//                                    ns3::MakeDoubleChecker<double> (0.1, 100.0));

static ns3::GlobalValue g_outageThreshold ("outageThreshold",
                                           "SNR threshold for outage events [dB]", // use -1000.0 with NoAuto
                                           ns3::DoubleValue (-5.0),
                                           ns3::MakeDoubleChecker<double> ());

static ns3::GlobalValue g_numberOfRaPreambles (
    "numberOfRaPreambles",
    "how many random access preambles are available for the contention based RACH process",
    ns3::UintegerValue (40), // Indicated for TS use case, 52 is default
    ns3::MakeUintegerChecker<uint8_t> ());

static ns3::GlobalValue
    g_handoverMode ("handoverMode",
                    "HO euristic to be used,"
                    "can be only \"NoAuto\", \"FixedTtt\", \"DynamicTtt\",   \"Threshold\"",
                    ns3::StringValue ("NoAuto"), ns3::MakeStringChecker ());

static ns3::GlobalValue g_e2TermIp ("e2TermIp", "The IP address of the RIC E2 termination",
                                    ns3::StringValue ("10.0.2.10"), ns3::MakeStringChecker ());

static ns3::GlobalValue
    g_enableE2FileLogging ("enableE2FileLogging",
                           "If true, generate offline file logging instead of connecting to RIC",
                           ns3::BooleanValue (false), ns3::MakeBooleanChecker ());

static ns3::GlobalValue g_controlFileName ("controlFileName",
                                           "The path to the control file (can be absolute)",
                                           ns3::StringValue (""),
                                           ns3::MakeStringChecker ());


void my_function(NetDeviceContainer lteEnbDevs)
{
    Ptr<LteEnbRrc> m_rrc = DynamicCast<LteEnbNetDevice>(lteEnbDevs.Get(0))->GetRrc();  // LteEnbNetDevice
    auto ueMap = m_rrc->GetUeMap();
    uint16_t targetCellId = 3;
    NS_LOG_UNCOND ("\n m_rrc: " << m_rrc << " ueMapSize: " << ueMap.size());
    for (auto ue : ueMap)
    {
      uint64_t imsi = ue.second->GetImsi();
      NS_LOG_UNCOND (" ue: " << ue  << " " << typeid(ue).name() << " ue.second " << ue.second << " " << typeid(ue.second).name() << " ue.first: "  << ue.first << " " << typeid(ue.first).name() << " imsi: " << imsi);
      
      m_rrc->PerformHandoverToTargetCell (imsi, targetCellId);

    }
}

void PrintPosition (NodeContainer nodeCantainer, Time period)
{
  for (uint32_t u = 0; u < nodeCantainer.GetN (); ++u)
  {
    Ptr<Node> node = nodeCantainer.Get (u);
    Vector pos = node->GetObject<MobilityModel>()->GetPosition();
    NS_LOG_UNCOND ("At time = " << Simulator::Now ().ToDouble(Time::S) << ", Node " << u << " position is " << pos);
  }
  Simulator::Schedule (period, &PrintPosition, nodeCantainer, period);
}


int
main (int argc, char *argv[])
{
  std::string traceFile = "/home/yizhou/桌面/SUMODEMO/SimpleDemo/MultiVehicle/Highway/exp=3/traceFile.txt";
  // std::string traceFile = "/home/yizhou/桌面/SUMODEMO/SimpleDemo/MultiVehicle/rsu_m=6/traceFile.txt";

  LogComponentEnableAll (LOG_PREFIX_ALL);
  // LogComponentEnable ("LteEnbNetDevice", LOG_LEVEL_INFO);

  // LogComponentEnable ("LteEnbRrc", LOG_LEVEL_DEBUG);
  // LogComponentEnable ("KpmIndication", LOG_LEVEL_ALL);
  // LogComponentEnable ("MmWaveEnbPhy", LOG_LEVEL_LOGIC);
  // Command line arguments
  CommandLine cmd (__FILE__);
  cmd.AddValue ("traceFile", "trace file", traceFile);
  cmd.Parse (argc, argv);

  bool harqEnabled = true;

  UintegerValue uintegerValue;
  BooleanValue booleanValue;
  StringValue stringValue;
  DoubleValue doubleValue;

  GlobalValue::GetValueByName ("hoSinrDifference", doubleValue);
  double hoSinrDifference = doubleValue.Get ();
  GlobalValue::GetValueByName ("bufferSize", uintegerValue);
  uint32_t bufferSize = uintegerValue.Get ();
  GlobalValue::GetValueByName ("enableTraces", booleanValue);
  bool enableTraces = booleanValue.Get ();
  GlobalValue::GetValueByName ("outageThreshold", doubleValue);
  double outageThreshold = doubleValue.Get ();
  GlobalValue::GetValueByName ("handoverMode", stringValue);
  std::string handoverMode = stringValue.Get ();
  GlobalValue::GetValueByName ("e2TermIp", stringValue);
  std::string e2TermIp = stringValue.Get ();
  GlobalValue::GetValueByName ("enableE2FileLogging", booleanValue);
  bool enableE2FileLogging = booleanValue.Get ();
  GlobalValue::GetValueByName ("numberOfRaPreambles", uintegerValue);
  uint8_t numberOfRaPreambles = uintegerValue.Get ();

  NS_LOG_UNCOND ("bufferSize " << bufferSize << " OutageThreshold " << outageThreshold
                               << " HandoverMode " << handoverMode << " e2TermIp " << e2TermIp
                               << " enableE2FileLogging " << enableE2FileLogging);

  GlobalValue::GetValueByName ("e2lteEnabled", booleanValue);
  bool e2lteEnabled = booleanValue.Get ();
  GlobalValue::GetValueByName ("e2nrEnabled", booleanValue);
  bool e2nrEnabled = booleanValue.Get ();
  GlobalValue::GetValueByName ("e2du", booleanValue);
  bool e2du = booleanValue.Get ();
  GlobalValue::GetValueByName ("e2cuUp", booleanValue);
  bool e2cuUp = booleanValue.Get ();
  GlobalValue::GetValueByName ("e2cuCp", booleanValue);
  bool e2cuCp = booleanValue.Get ();

  GlobalValue::GetValueByName ("reducedPmValues", booleanValue);
  bool reducedPmValues = booleanValue.Get ();

  GlobalValue::GetValueByName ("indicationPeriodicity", doubleValue);
  double indicationPeriodicity = doubleValue.Get ();
  GlobalValue::GetValueByName ("controlFileName", stringValue);
  std::string controlFilename = stringValue.Get ();

  NS_LOG_UNCOND ("e2lteEnabled " << e2lteEnabled << " e2nrEnabled " << e2nrEnabled << " e2du "
                                 << e2du << " e2cuCp " << e2cuCp << " e2cuUp " << e2cuUp
                                 << " controlFilename " << controlFilename
                                 << " indicationPeriodicity " << indicationPeriodicity);

  Config::SetDefault ("ns3::LteEnbNetDevice::ControlFileName", StringValue (controlFilename));
  Config::SetDefault ("ns3::LteEnbNetDevice::E2Periodicity", DoubleValue (indicationPeriodicity));
  Config::SetDefault ("ns3::MmWaveEnbNetDevice::E2Periodicity",
                      DoubleValue (indicationPeriodicity));

  Config::SetDefault ("ns3::MmWaveHelper::E2ModeLte", BooleanValue (e2lteEnabled));
  Config::SetDefault ("ns3::MmWaveHelper::E2ModeNr", BooleanValue (e2nrEnabled));

  // The DU PM reports should come from both NR gNB as well as LTE eNB,
  // since in the RLC/MAC/PHY entities are present in BOTH NR gNB as well as LTE eNB.
  // DU reports from LTE eNB are not implemented in this release
  Config::SetDefault ("ns3::MmWaveEnbNetDevice::EnableDuReport", BooleanValue (e2du));

  // The CU-UP PM reports should only come from LTE eNB, since in the NS3 “EN-DC
  // simulation (Option 3A)”, the PDCP is only in the LTE eNB and NOT in the NR gNB
  Config::SetDefault ("ns3::MmWaveEnbNetDevice::EnableCuUpReport", BooleanValue (e2cuUp));
  Config::SetDefault ("ns3::LteEnbNetDevice::EnableCuUpReport", BooleanValue (false));

  Config::SetDefault ("ns3::MmWaveEnbNetDevice::EnableCuCpReport", BooleanValue (e2cuCp));
  Config::SetDefault ("ns3::LteEnbNetDevice::EnableCuCpReport", BooleanValue (false));

  Config::SetDefault ("ns3::MmWaveEnbNetDevice::ReducedPmValues", BooleanValue (reducedPmValues));
  Config::SetDefault ("ns3::LteEnbNetDevice::ReducedPmValues", BooleanValue (reducedPmValues));

  Config::SetDefault ("ns3::LteEnbNetDevice::EnableE2FileLogging",
                      BooleanValue (enableE2FileLogging));
  Config::SetDefault ("ns3::MmWaveEnbNetDevice::EnableE2FileLogging",
                      BooleanValue (enableE2FileLogging));

  Config::SetDefault ("ns3::MmWaveEnbMac::NumberOfRaPreambles",
                      UintegerValue (numberOfRaPreambles));

  Config::SetDefault ("ns3::MmWaveHelper::HarqEnabled", BooleanValue (harqEnabled));
  Config::SetDefault ("ns3::MmWaveHelper::UseIdealRrc", BooleanValue (true));
  Config::SetDefault ("ns3::MmWaveHelper::E2TermIp", StringValue (e2TermIp));

  // Config::SetDefault ("ns3::MmWaveFlexTtiMaxRateMacScheduler::HarqEnabled", BooleanValue (harqEnabled));
  Config::SetDefault ("ns3::MmWaveFlexTtiMacScheduler::HarqEnabled", BooleanValue (harqEnabled));
  Config::SetDefault ("ns3::MmWavePhyMacCommon::NumHarqProcess", UintegerValue (100));
  Config::SetDefault ("ns3::MmWavePhyMacCommon::HarqDlTimeout", UintegerValue (10));
  //Config::SetDefault ("ns3::MmWaveBearerStatsCalculator::EpochDuration", TimeValue (MilliSeconds (10.0)));

  // set to false to use the 3GPP radiation pattern (proper configuration of the bearing and downtilt angles is needed)
//   Config::SetDefault ("ns3::ThreeGppAntennaArrayModel::IsotropicElements", BooleanValue (true));
  Config::SetDefault ("ns3::ThreeGppChannelModel::UpdatePeriod", TimeValue (MilliSeconds (100.0)));
  Config::SetDefault ("ns3::ThreeGppChannelConditionModel::UpdatePeriod",
                      TimeValue (MilliSeconds (100)));

  Config::SetDefault ("ns3::LteRlcAm::ReportBufferStatusTimer", TimeValue (MilliSeconds (10.0)));
  Config::SetDefault ("ns3::LteRlcUmLowLat::ReportBufferStatusTimer",
                      TimeValue (MilliSeconds (10.0)));
  Config::SetDefault ("ns3::LteRlcUm::MaxTxBufferSize", UintegerValue (bufferSize * 1024 * 1024));
  Config::SetDefault ("ns3::LteRlcUmLowLat::MaxTxBufferSize",
                      UintegerValue (bufferSize * 1024 * 1024));
  Config::SetDefault ("ns3::LteRlcAm::MaxTxBufferSize", UintegerValue (bufferSize * 1024 * 1024));

  Config::SetDefault ("ns3::LteEnbRrc::OutageThreshold", DoubleValue (outageThreshold));
  Config::SetDefault ("ns3::LteEnbRrc::SecondaryCellHandoverMode", StringValue (handoverMode));
  Config::SetDefault ("ns3::LteEnbRrc::HoSinrDifference", DoubleValue (hoSinrDifference));

  int numerology = 2; //3
  // Carrier bandwidth in Hz
  double bandwidth = 50e6;         //20e6;400e6
  // // Center frequency in Hz
  double centerFrequency = 28e9;    //3.5e9;28e9

  // Number of antennas in each UE
  int numAntennasMcUe = 1;  //4
  // Number of antennas in each mmWave BS
  int numAntennasMmWave = 4; //16

  double rsuTxPower = 30;
  double ueTxPower = 23;

  Ptr<MmWaveHelper> mmwaveHelper = CreateObject<MmWaveHelper> ();
  mmwaveHelper->SetSchedulerType ("ns3::MmWaveFlexTtiMacScheduler");
  mmwaveHelper->SetPathlossModelType ("ns3::ThreeGppUmaPropagationLossModel");
  mmwaveHelper->SetChannelConditionModelType ("ns3::AlwaysLosChannelConditionModel");

  // Set the number of antennas in the devices
  mmwaveHelper->SetUePhasedArrayModelAttribute("NumColumns", UintegerValue(std::sqrt(numAntennasMcUe)));
  mmwaveHelper->SetUePhasedArrayModelAttribute("NumRows", UintegerValue(std::sqrt(numAntennasMcUe)));
  mmwaveHelper->SetEnbPhasedArrayModelAttribute("NumColumns",UintegerValue(std::sqrt(numAntennasMmWave)));
  mmwaveHelper->SetEnbPhasedArrayModelAttribute("NumRows", UintegerValue(std::sqrt(numAntennasMmWave)));
  Config::SetDefault ("ns3::MmWavePhyMacCommon::Bandwidth", DoubleValue (bandwidth));
  Config::SetDefault ("ns3::MmWavePhyMacCommon::CenterFreq", DoubleValue (centerFrequency));
  Config::SetDefault ("ns3::MmWavePhyMacCommon::Numerology", EnumValue (numerology));
  Config::SetDefault ("ns3::MmWaveEnbPhy::TxPower", DoubleValue (rsuTxPower));
  Config::SetDefault ("ns3::MmWaveUePhy::TxPower", DoubleValue (ueTxPower));
 
  Ptr<MmWavePointToPointEpcHelper> epcHelper = CreateObject<MmWavePointToPointEpcHelper> ();
  mmwaveHelper->SetEpcHelper (epcHelper);

  std::fstream trace;
  trace.open (traceFile, std::ios::in);
  if (!trace){
    std::cerr << "Unable to open file!" << std::endl;
    return 1;
  }
  std::string line;
  int nUeNodes = 0;
  // auto isSpace = [](u_char c) {return std::isspace(c);};
  while (std::getline(trace, line)) if (line.empty()) ++nUeNodes;
  
  // trace.close();
  NodeContainer ueNodes;
  ueNodes.Create (nUeNodes);
  MobilityHelper uemobility;
  uemobility.SetMobilityModel ("ns3::WaypointMobilityModel");
  uemobility.Install (ueNodes);
  nUeNodes = -1;
  trace.clear();              
  trace.seekg(0, std::ios::beg);
  double simTime = 0.0;
  // std::map <uint64_t, double> imsiArrivalTime;
  for (uint32_t u = 0; u < ueNodes.GetN (); ++u){
    imsiArrivalTime[u+1] = 0.0;
  }

  while (std::getline(trace, line)){
    if (line.empty()) {
      ++nUeNodes;
      continue;
    }
    float time, x, y;
    std::istringstream iss(line);
    if (!(iss >> time >> x >> y)){
      std::cerr << "Warning: Format" << line << std::endl;
      continue;
    }
    else {
      ueNodes.Get (nUeNodes)->GetObject<WaypointMobilityModel>()->AddWaypoint (Waypoint (Seconds (time), Vector (x, y, 0.00)));
      if (simTime < time) {
        simTime = time;
        // imsiRunningTime[nUeNodes+1] = time;
      }
      imsiRunningTime[nUeNodes+1] = time;
      if (imsiArrivalTime[nUeNodes+1] == 0){
        imsiArrivalTime[nUeNodes+1] = time;
        // NS_LOG_UNCOND("UE " << nUeNodes+1 << ", imsiArrivalTime " << imsiArrivalTime[nUeNodes+1]);
      }
      // NS_LOG_UNCOND ("Time: " << Seconds (time) << " Position: " << Vector (x, y, 0.00));
    }    
  }

  // for (uint32_t u = 0; u < ueNodes.GetN (); ++u){
  //   NS_LOG_UNCOND ("UE_" << u << " Position: " << ueNodes.Get(u)->GetObject<MobilityModel>()->GetPosition());
  // }
  uint16_t length = 2000;
  uint16_t diff = 100;
  uint16_t nMmWaveEnbNodes = length / diff /2;
  uint8_t nLteEnbNodes = 1;

  // Get SGW/PGW and create a single RemoteHost
  Ptr<Node> pgw = epcHelper->GetPgwNode ();
  NodeContainer remoteHostContainer;
  remoteHostContainer.Create (1);
  Ptr<Node> remoteHost = remoteHostContainer.Get (0);
  InternetStackHelper internet;
  internet.Install (remoteHostContainer);

  // Create the Internet by connecting remoteHost to pgw. Setup routing too
  PointToPointHelper p2ph;
  p2ph.SetDeviceAttribute ("DataRate", DataRateValue (DataRate ("100Gb/s")));
  p2ph.SetDeviceAttribute ("Mtu", UintegerValue (2500));
  p2ph.SetChannelAttribute ("Delay", TimeValue (Seconds (0.010)));
  NetDeviceContainer internetDevices = p2ph.Install (pgw, remoteHost);
  Ipv4AddressHelper ipv4h;
  ipv4h.SetBase ("1.0.0.0", "255.0.0.0");
  Ipv4InterfaceContainer internetIpIfaces = ipv4h.Assign (internetDevices);
  // interface 0 is localhost, 1 is the p2p device
  Ipv4Address remoteHostAddr = internetIpIfaces.GetAddress (1);
  Ipv4StaticRoutingHelper ipv4RoutingHelper;
  Ptr<Ipv4StaticRouting> remoteHostStaticRouting =
      ipv4RoutingHelper.GetStaticRouting (remoteHost->GetObject<Ipv4> ());
  remoteHostStaticRouting->AddNetworkRouteTo (Ipv4Address ("7.0.0.0"), Ipv4Mask ("255.0.0.0"), 1);

  NS_LOG_UNCOND ("Number of UEs: " << nUeNodes + 1 << " Number of gnbs: " << nMmWaveEnbNodes);
  // Position
  NodeContainer mmWaveEnbNodes;
  NodeContainer lteEnbNodes;
  NodeContainer allEnbNodes;
  mmWaveEnbNodes.Create (nMmWaveEnbNodes);
  lteEnbNodes.Create (nLteEnbNodes);
  allEnbNodes.Add (lteEnbNodes);
  allEnbNodes.Add (mmWaveEnbNodes);
  
  uint8_t y_center = 0;
    // Install Mobility Model
  Ptr<ListPositionAllocator> enbPositionAlloc = CreateObject<ListPositionAllocator> ();
  enbPositionAlloc->Add (Vector (length / 2, y_center - 12, 35));
  for (uint32_t u = 0; u  < mmWaveEnbNodes.GetN(); ++u)
    {
      enbPositionAlloc->Add (Vector (u * diff * 2 + diff, y_center + std::pow (-1, u) * 12, 10));
    }
  MobilityHelper enbmobility;
  enbmobility.SetMobilityModel ("ns3::ConstantPositionMobilityModel");
  enbmobility.SetPositionAllocator (enbPositionAlloc);
  enbmobility.Install (allEnbNodes);

 // Install mmWave, lte, mc Devices to the nodes
  NetDeviceContainer lteEnbDevs = mmwaveHelper->InstallLteEnbDevice (lteEnbNodes);
  NetDeviceContainer mmWaveEnbDevs = mmwaveHelper->InstallEnbDevice (mmWaveEnbNodes);
  NetDeviceContainer mcUeDevs = mmwaveHelper->InstallMcUeDevice (ueNodes);

  // Install the IP stack on the UEs
  internet.Install (ueNodes);
  Ipv4InterfaceContainer ueIpIface;
  ueIpIface = epcHelper->AssignUeIpv4Address (NetDeviceContainer (mcUeDevs));
  // Assign IP address to UEs, and install applications
  for (uint32_t u = 0; u < ueNodes.GetN (); ++u)
    {
      Ptr<Node> ueNode = ueNodes.Get (u);
      // Set the default gateway for the UE
      Ptr<Ipv4StaticRouting> ueStaticRouting =
          ipv4RoutingHelper.GetStaticRouting (ueNode->GetObject<Ipv4> ());
      ueStaticRouting->SetDefaultRoute (epcHelper->GetUeDefaultGatewayAddress (), 1);
    }

  // Add X2 interfaces
  mmwaveHelper->AddX2Interface (lteEnbNodes, mmWaveEnbNodes);

  // Manual attachment
  mmwaveHelper->AttachToClosestEnb (mcUeDevs, mmWaveEnbDevs, lteEnbDevs);

  // Install and start applications
  // On the remoteHost there is UDP OnOff Application

  uint16_t portUdp = 60000;
  Address sinkLocalAddressUdp (InetSocketAddress (Ipv4Address::GetAny (), portUdp));
  PacketSinkHelper sinkHelperUdp ("ns3::UdpSocketFactory", sinkLocalAddressUdp);
  AddressValue serverAddressUdp (InetSocketAddress (remoteHostAddr, portUdp));

  ApplicationContainer sinkApp;
  sinkApp.Add (sinkHelperUdp.Install (remoteHost));

  for (uint32_t u = 0; u < ueNodes.GetN (); ++u)
    {

      PacketSinkHelper dlPacketSinkHelper ("ns3::UdpSocketFactory",
                                           InetSocketAddress (Ipv4Address::GetAny (), 1234 + u));
      sinkApp.Add (dlPacketSinkHelper.Install (ueNodes.Get (u)));
      OnOffHelper onOffAppUrllc ("ns3::UdpSocketFactory", InetSocketAddress (ueIpIface.GetAddress (u), 1234 + u));
      onOffAppUrllc.SetAttribute ("PacketSize", UintegerValue (300));   
      // onOffAppUrllc.SetAttribute ("DataRate", StringValue ("210kbps"));
      onOffAppUrllc.SetAttribute ("DataRate", StringValue ("5Mbps")); 
      onOffAppUrllc.SetAttribute ("OnTime",  StringValue ("ns3::ExponentialRandomVariable[Mean=0.01]"));
      onOffAppUrllc.SetAttribute ("OffTime", StringValue ("ns3::ConstantRandomVariable[Constant=0]"));
      
      ApplicationContainer appContainer = onOffAppUrllc.Install(remoteHost);
      Ptr<Application> app = appContainer.Get(0);
      app->SetStartTime(Seconds (imsiArrivalTime[u+1] + 0.1));
      app->SetStopTime(Seconds(imsiRunningTime[u + 1] - 0.1));
    }

  // Start applications
  // GlobalValue::GetValueByName ("simTime", doubleValue);
  // double simTime = doubleValue.Get ();
  sinkApp.Start (Seconds (0));
  
  // FlowMonitorHelper flowmon;
  // Ptr<FlowMonitor> monitor = flowmon.InstallAll ();

  // Config::SetDefault ("ns3::ConfigStore::Filename", StringValue ("available-paths.txt"));
  // Config::SetDefault ("ns3::ConfigStore::FileFormat", StringValue ("RawText"));
  // Config::SetDefault ("ns3::ConfigStore::Mode", StringValue ("Save"));

  // ConfigStore outputConfig;
  // outputConfig.ConfigureAttributes ();

  if (enableTraces)
    {
      mmwaveHelper->EnableTraces ();
    }


  bool run = true;
  if (run)
    {
      NS_LOG_UNCOND ("Simulation time is " << simTime << " seconds ");
      Simulator::Stop (Seconds (simTime));
      NS_LOG_INFO ("Run Simulation.");
      Simulator::Run ();

    }
  // monitor->CheckForLostPackets ();
  // monitor->SerializeToXmlFile("flowmon-results.xml", true, true);
  Simulator::Destroy ();
  return 0;
}