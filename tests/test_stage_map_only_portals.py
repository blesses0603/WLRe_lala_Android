"""Synthetic desktop portal fixtures reused by portable runtime tests."""
import os

import struct

import unittest

from types import SimpleNamespace

from unittest.mock import Mock, patch

from wlre.services.world.boundary_portals import boundary_portal_bindings

from wlre.services.world.portal_evidence_1275 import read_only_stage_portal_markers

from wlre.services.world.portal_dedup_1275 import collapse_portal_destinations

from wlre.services.world.portals import Portals, marked_portals

from wlre.services.world.portal_policy import destination_problem

from wlre.services.world.portal_travel import PortalTravel

from wlre.services.world.portal_coverage import audit_portal_coverage

from wlre.core.state import State

from wlre.network.wire import ProtocolError

def marker(*rows):
    return struct.pack('<i',len(rows))+b''.join(struct.pack('<HBHIHHIB',*r) for r in rows)

def fixture(kind=2, *, links=None, rows=None, doors=None):
    # Historical Cairo-like coordinates, with synthetic rectangular geometry.
    stages={12500:dict(pos_x_ratio=2,pos_y_ratio=4,map_width=10000,map_height=12000,
                       small_offset_x=0,small_offset_y=0),58001:{},60014:{},12501:{}}
    doors=doors if doors is not None else {12500:[
        dict(index=1,x=159,y=96,right=161,bottom=98,sign_x=0,sign_y=0,
             sign_type=1,event_ids=[1],touch_event_ids=[1]),
        dict(index=2,x=5,y=100,right=6,bottom=101,sign_x=0,sign_y=0,
             sign_type=1,event_ids=[5],touch_event_ids=[5])]}
    event_id=58001 if kind==3 else 1
    raw=marker(*(rows if rows is not None else [(12500,kind,0,event_id,3177,1920,10,0)]))
    positions,targets=boundary_portal_bindings(raw,links,doors,stages)
    runtime=SimpleNamespace(revision=1286,doors=doors,portal_positions=positions,
        portal_destinations=targets,portal_stage_markers=read_only_stage_portal_markers(raw,stages),
        texts={10:'往航海大地圖'},scene_names={12500:'開羅',58001:'航海大地圖',60014:'埃及野外'},
        portal_names={(12500,event_id):'往航海大地圖'})
    with patch('wlre.services.world.runtime_1275.baseline_revision',return_value='1286'), \
         patch('wlre.services.world.catalog_source_policy.official_runtime',return_value=runtime):
        catalog=Portals()
    return SimpleNamespace(raw=raw,links=links,stages=stages,doors=doors,
                           positions=positions,targets=targets,catalog=catalog)

def projection(row):
    return SimpleNamespace(**row['projection_guard'],packet_to_pixel=lambda x,y:(x/10,y/10))
