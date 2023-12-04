# Import some POX stuff
from pox.core import core                     # Main POX object
import pox.openflow.libopenflow_01 as of      # OpenFlow 1.0 library
import pox.lib.packet as pkt                  # Packet parsing/construction
from pox.lib.addresses import EthAddr, IPAddr # Address types
import pox.lib.util as poxutil                # Various util functions
import pox.lib.revent as revent               # Event library
import pox.lib.recoco as recoco               # Multitasking library
from pox.lib.util import dpid_to_str
import pox.openflow.discovery

import math

log = core.getLogger()
DT = 5

'''
Find nodes in graph g that can be reached from node v.
'''
def get_neighbors(g,v):
  neighbors=[]
  for c,pn in g.keys():
    if c is v:
      neighbors.append(pn)
  return neighbors

'''
Find a path in graph, g from start node s to goal node e.
Return a sequence of nodes as a list.
'''
def find_paths(g, s, e, path=[]):
  path=path+[s]
  if s is e:
    return [path]
  paths=[]
  neighbors=get_neighbors(g,s)
  for w in neighbors:
    if w not in path:
      new_paths=find_paths(g,w,e,path)
      for newpath in new_paths:
        paths.append(newpath)
  return paths

'''
Determine links in a path.
Return a list of links where each link is (dpid1, port1, dpid2, port2)
'''
def links_from_path(g, path):
  links=[]
  for i in range(len(path)-1):
    link=(path[i],g[path[i],path[i+1]],path[i+1],g[path[i+1],path[i]])
    links.append(link)
  return links

'''
Calculate total link utilization for a path.
'''
def path_utilization(utilization, links):
  total_util=0
  for dpid1, port1, dpid2, port2 in links:
    half_link_a= utilization.get((dpid1,port1),0)
    half_link_b= utilization.get((dpid2,port2),0)
    total_util = total_util + half_link_a + half_link_b
  return total_util

'''
Get some (hopefully unique) integer identifier from a given EthAddr.
To avoid identifier collisions Mininet should be run with the --mac option.
Furthermore hosts and switches should be named h_j, s_i where there is no overlap between i and j.
'''
def etoi(ethaddr):
  sethr=str(ethaddr)
  string_bytes=sethr.split(':')
  sixth_byte=string_bytes[-1]
  uid=int(sixth_byte,16)
  return uid
  
class Component(object):
  def __init__(self):
    #Hard code switch host links. Is it possible to discover these links at runtime (ARP, LLDP, etc.)?
    self.e={ 
      (1,3):0,
      (3,1):1,
      (2,6):0,
      (6,2):3
    }
    #Should these be dynamically discovered? Probably.
    self.ip_to_mac={ 
      IPAddr('10.0.0.1'):EthAddr('00:00:00:00:00:01'),
      IPAddr('10.0.0.2'):EthAddr('00:00:00:00:00:02'),
    }
    self.connections=[]
    self.timer=recoco.Timer(DT,self.send_stats_requests,recurring=True)
    self.utilization={}
    self.port_stats={}
    def startup():
      core.openflow.addListeners(self)
      core.openflow_discovery.addListeners(self)
      core.host_tracker.addListeners(self)
    core.call_when_ready(startup, ('openflow','openflow_discovery','host_tracker'))

  '''
  Send an OpenFlow Protocol port statistics request. 
  This is called at a fixed time interval defined by self.timer.
  '''
  def send_stats_requests(self):
    for connection in self.connections:
      msg=of.ofp_stats_request()
      msg.type=of.OFPST_PORT
      msg.body=of.ofp_port_stats_request()
      connection.send(msg)

  '''
  Update the utilization of each (dpid:port).
  '''
  def _handle_PortStatsReceived(self,event):
    for stat in event.stats:
      if stat.port_no==65534:
        continue
      if self.utilization.get((event.dpid,stat.port_no)) is None:
        continue
      new_utilization=(stat.tx_bytes - self.utilization[(event.dpid,stat.port_no)])/DT

      self.utilization[(event.dpid,stat.port_no)]=stat.tx_bytes
      self.port_stats[(event.dpid,stat.port_no)]=new_utilization

  def _handle_ConnectionUp(self, event):
    self.connections.append(event.connection)

  def _handle_PacketIn(self, event):
    packet = event.parsed
    
    # Handle ARP REQUEST with hard-coded IP:MAC addresses:
    if packet.type==packet.ARP_TYPE:
      if packet.payload.opcode==pkt.arp.REQUEST:
        ethsrc=self.ip_to_mac[packet.payload.protodst]
        # BUILD REPLY
        arp_reply=pkt.arp()
        arp_reply.hwsrc=ethsrc
        arp_reply.hwdst=packet.src
        arp_reply.opcode=pkt.arp.REPLY
        arp_reply.protosrc=packet.payload.protodst
        arp_reply.protodst=packet.payload.protosrc
        ether=pkt.ethernet()
        ether.type=pkt.ethernet.ARP_TYPE
        ether.dst=packet.src
        ether.src=ethsrc
        ether.set_payload(arp_reply)
        # SEND REPLY
        msg=of.ofp_packet_out()
        msg.data=ether.pack()
        msg.actions.append(of.ofp_action_output(port=of.OFPP_IN_PORT))
        msg.in_port=event.port
        event.connection.send(msg)
    else:
      #1) Generate paths from source to destination.
      src=etoi(packet.src)
      dst=etoi(packet.dst)
      possible_paths=find_paths(self.e,src,dst)

      #2) Choose optimum path based on network utilization.
      i=0
      min_util=math.inf
      total_util=0
      for j, path in enumerate(possible_paths):
        links=links_from_path(self.e,path)
        path_util=path_utilization(self.port_stats,links)
        total_util+=path_util
        if path_util<min_util:
          i=j
          min_util=path_util
      
      optimum_path=possible_paths[i]
      # The average path utilization is the average utilization of each path in the possible paths,
      # excluding the chosen path.
      avg_path_util=(total_util-min_util)/(len(possible_paths)-1)
      
      log.debug("[Opimum Path: %s Util: %s AVG Util: %s", optimum_path,min_util,avg_path_util)
      
      #3) Install flow-modifications to switches in the path.
      for i in range(1, len(optimum_path)-1):
        dpid_c=optimum_path[i]
        dpid_n=optimum_path[i+1]
        out_port=self.e[(dpid_c,dpid_n)]

        connection=core.openflow.getConnection(dpid_c)

        # Match on packets that arrive from the specified source to the destination.
        msg=of.ofp_flow_mod()
        msg.match.dl_dst=packet.dst
        msg.match.dl_src=packet.src
        msg.idle_timeout=3
        msg.hard_timeout=6
        msg.actions.append(of.ofp_action_output(port=out_port))
        connection.send(msg)

        # Send the received packet to the next switch.
        if i == 1:
          msg=of.ofp_packet_out(data=event.ofp)
          msg.actions.append(of.ofp_action_output(port=out_port))
          event.connection.send(msg)
        
      
  def _handle_LinkEvent(self, event):
    link = event.link
    '''
    Track discovered link as an edge so that
    the link described by dpid1,dpid2,port1,port2 is represented by the following two edges:
    edge_1 {(dpid1, dpid2):port1}
    edge_2 {(dpid2, dpid1):port2}
    This only registers links between switches. Need to handle links between a switch and host elsewhere.
    '''
    self.e[(link.dpid1,link.dpid2)]=link.port1
    self.e[(link.dpid2,link.dpid1)]=link.port2
    # Initialize some dictionary keys for utilization.
    self.utilization[(link.dpid1,link.port1)]=0
    self.utilization[(link.dpid2,link.port2)]=0

    
    
def launch():
  core.registerNew(Component)
  import pox.openflow.discovery
  pox.openflow.discovery.launch()
  import pox.host_tracker
  pox.host_tracker.launch()
    
    
