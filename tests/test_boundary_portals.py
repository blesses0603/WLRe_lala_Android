"""Synthetic desktop portal fixtures reused by portable runtime tests."""
import struct

from types import SimpleNamespace

import unittest

from unittest.mock import Mock, patch

from wlre.core.state import State

from wlre.network.wire import Writer

from wlre.services.world.boundary_portals import boundary_portal_bindings, touch_bounds

from wlre.services.world.doors_1275 import parse_verified_doors, DoorSourceError

from wlre.services.world.portal_travel import PortalTravel

from wlre.services.world.portals import Portals

def marker(*rows):
    return struct.pack('<i',len(rows))+b''.join(struct.pack('<HBHIHHIB',*r) for r in rows)

def stages():
    return {60000:{'pos_x_ratio':2,'pos_y_ratio':4,'map_width':9000,'map_height':15000,
                   'small_offset_x':0,'small_offset_y':0},
            58001:{'pos_x_ratio':2,'pos_y_ratio':4},11016:{},12000:{}}

def links():
    return ('事件ID=60000\n原場景位置[X:1759,Y:2701][11016][X:1,Y:2]\n'
            '原場景位置[X:2961,Y:3141][12000][X:1,Y:2]\n'
            '原場景位置[X:60,Y:1100][58001][X:7453,Y:8461]\n').encode('utf-16-le')

def door(**kw):
    return dict(index=3,x=1,y=1,right=8,bottom=112,sign_type=4,sign_x=0,sign_y=0,
                col_x=0,col_y=0,col_z=0,event_ids=[7],touch_event_ids=[7],**kw)

def eve_fixture(*,occur=2,events=None):
    # Eleven full v115 sections, including real NewDoor/NewEvent tails.
    common=bytes(20)+b'\x00'+struct.pack('<II',1,1)+b'\x01\x07\x00\x00'
    d=struct.pack('<H',3)+common+struct.pack('<IIBIIIII',8,112,4,0,0,0,0,0)
    event=(struct.pack('<HB',7,occur)+bytes(20)+b'\x01'+bytes(22)+b'\x02'+bytes(44))
    sections=[b'\x00\x00',b'\x01\x00'+d,b'\x00\x00',b'\x00\x00',
              struct.pack('<H',len(events or [event]))+b''.join(events or [event])]
    sections += [b'\x00\x00']*6
    offset=4;table=[]
    for section in sections:table.append(offset);offset+=len(section)
    scene=struct.pack('<HH',99,115)+b''.join(sections)+struct.pack('<11I',*table)
    return bytes(8)+struct.pack('<IHHII',1,60000,99,24,len(scene))+scene
