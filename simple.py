"""Custom topology example

Two directly connected switches plus a host for each switch:

   host --- switch --- switch --- host

Adding the 'topos' dict with a key/value pair to generate our newly defined
topology enables one to pass in '--topo=mytopo' from the command line.
"""

from mininet.topo import Topo
from mininet.link import TCLink

class MyTopo( Topo ):
    "Simple topology example."

    def build( self ):
        "Create custom topo."

        # Add hosts and switches
        h1 = self.addHost( 'h1' )
        h2 = self.addHost( 'h2' )
        s3 = self.addSwitch( 's3' )
        s4 = self.addSwitch( 's4' )
        s5 = self.addSwitch( 's5' )
        s6 = self.addSwitch( 's6' )
        s7 = self.addSwitch( 's7' )
        s8 = self.addSwitch( 's8' )

        # Add links
        '''
        self.addLink( h1, s3 )
        self.addLink( s3, s4 )
        self.addLink( s3, s8 )
        self.addLink( s4, s5 )
        self.addLink( s4, s7 )
        self.addLink( s8, s5 )
        self.addLink( s8, s7 )
        self.addLink( s5, s6 )
        self.addLink( s7, s6 )
        self.addLink( s6, h2 )
        '''

        self.addLink( h1, s3, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s3, s4, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s3, s8, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s4, s5, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s4, s7, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s8, s5, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s8, s7, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s5, s6, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s7, s6, cls=TCLink, bw=5, delay='10ms')
        self.addLink( s6, h2, cls=TCLink, bw=5, delay='10ms')


topos = { 'mytopo': ( lambda: MyTopo() ) }
