#!/bin/sh
# Wake the curved Samsung UN55MU6500 (7C:64:56:13:A2:F9) from deep standby.
/usr/local/bin/python3 -c 'import socket; p=b"\xff"*6+bytes.fromhex("7c645613a2f9")*16; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1); s.sendto(p,("192.168.1.255",9))'
