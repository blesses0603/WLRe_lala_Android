"""Android v0.5.12 non-NPC parity: side effects require server evidence."""
import unittest

from android_app.features import GAME_COMMANDS, checked_command
from wlre.core.state import State
from wlre.network.client import SessionLogic
from wlre.network.protocol import decode
from wlre.network.wire import Packet, Writer, ProtocolError
from wlre.services.instance_room_flow import coop_completed_no_chest
from wlre.services.battle.attribute_points import expire as expire_points


def ready():
    state=State(phase='world_ready',initial_data_complete=True)
    state.player={'role_id':678,'scene':12000}
    return state,SessionLogic()


def reward(open_reward=1,mark=1):
    return decode(Packet(186,11,Writer().u8(3).u8(3)
                        .u8(open_reward).u8(mark).u8(0).build()))


def members(rid):
    return {'type':'instance_members','mode':'coop','room_id':rid,
            'host_id':678,'standby':True,'kind':1,'npc_id':0,
            'capacity':1,'members':[{'role_id':678}]}


class NonNpcInstanceSafety(unittest.TestCase):
    def test_reward_before_first_room_snapshot_must_survive(self):
        state,logic=ready()
        state.apply(reward())
        self.assertTrue(state.instances['coop']['completed'])
        state.apply(members(23))
        self.assertEqual(state.instances['coop']['reward']['open_reward'],1)
        self.assertEqual(state.instances['coop']['completion_source'],'S186-11')

    def test_new_room_clears_only_settled_old_reward(self):
        state,_=ready()
        state.apply(members(23))
        state.apply(reward(open_reward=0,mark=0))
        state.apply(members(24))
        self.assertIsNone(state.instances['coop']['reward'])
        state.apply(reward())
        state.instances['coop']['claim_pending']={'started':1,'fingerprint':(3,3,1,1,0)}
        state.apply(members(25))
        self.assertIsNotNone(state.instances['coop']['claim_pending'])
        self.assertEqual(state.instances['coop']['reward']['open_reward'],1)

    def test_coop_leave_does_not_guess_missing_reward(self):
        state,logic=ready();logic.world_acknowledged=True
        state.apply(members(23))
        state.instances['coop']['phase']='matched'
        state.battle['post_event']={'status':'completed'}
        with self.assertRaises(ProtocolError):
            logic.command({'type':'instance_leave','mode':'coop'},state)
        state.apply(reward(open_reward=0,mark=0))
        self.assertTrue(coop_completed_no_chest(state.instances['coop']))
        self.assertEqual(logic.command({'type':'instance_leave','mode':'coop'},state),
                         [Packet(186,5)])
        with self.assertRaises(ProtocolError):
            logic.command({'type':'instance_leave','mode':'coop'},state)

    def test_manual_allocation_waits_for_ack_and_stat_recheck(self):
        state,logic=ready();logic.world_acknowledged=True
        stats={'int':11,'str':12,'con':13,'agi':14,'wis':15,'attribute_potential':2}
        state.knowledge['player']={'ready':True,'stats':stats.copy(),'skills':{}}
        command={'type':'allocate_points','increments':{'int':1},'baseline':stats.copy()}
        packets=logic.command(command,state)
        self.assertEqual(len(packets),1)
        self.assertEqual((packets[0].main,packets[0].sub),(8,1))
        self.assertTrue(state.attribute_allocation['pending'])
        with self.assertRaises(ProtocolError):
            logic.command(command,state)
        state.apply({'type':'attribute_allocation_success'})
        self.assertTrue(state.attribute_allocation['pending'])
        state.knowledge['player']['stats'].update(int=12,attribute_potential=1)
        state.apply({'type':'attribute_set','entity':'self',
                     'kind':25,'parameter':0,'value':120})
        self.assertFalse(state.attribute_allocation['pending'])
        self.assertFalse(state.attribute_allocation['uncertain'])

    def test_missing_allocation_ack_times_out_unknown(self):
        state,logic=ready();logic.world_acknowledged=True
        state.knowledge['player']={'ready':True,'stats':{
            'int':11,'str':12,'con':13,'agi':14,'wis':15,'attribute_potential':1}}
        before=dict(state.knowledge['player']['stats'])
        logic.command({'type':'allocate_points','increments':{'str':1},
                       'baseline':before},state)
        sent=state.attribute_allocation['sent_at']
        self.assertTrue(expire_points(state,now=sent+13))
        self.assertTrue(state.attribute_allocation['uncertain'])
        with self.assertRaises(ProtocolError):
            logic.command({'type':'allocate_points','increments':{'str':1},
                           'baseline':before},state)

    def test_roster_refresh_only_known_room_and_throttled(self):
        state,logic=ready();logic.world_acknowledged=True
        event={'type':'instance_phase','mode':'main','kind':1,'room_id':210,
               'host_id':678,'count':1}
        state.apply(event)
        self.assertEqual(logic.receive(event,state),
                         [Packet(85,4,Writer().u16(210).build())])
        self.assertEqual(logic.receive(event,state),[])
        state.apply(members(23))
        unwanted={'type':'instance_member_refresh_request','mode':'coop','room_id':99}
        wanted={**unwanted,'room_id':23}
        self.assertEqual(logic.receive(unwanted,state),[])
        self.assertEqual(logic.receive(wanted,state),
                         [Packet(186,8,Writer().u16(23).build())])
        self.assertEqual(logic.receive(wanted,state),[])

    def test_npc_still_explicitly_excluded_and_paid_reward_not_added(self):
        for kind in ('npc_start','npc_next','npc_choose','npc_shop',
                     'instance_reward_paid','instance_claim'):
            self.assertNotIn(kind,GAME_COMMANDS)
            with self.assertRaises(ValueError):
                checked_command({'type':kind})
        self.assertIn('instance_reward_claim',GAME_COMMANDS)
        self.assertIn('allocate_points',GAME_COMMANDS)
        self.assertFalse(State().instances['coop']['auto_claim_enabled'])

    def test_coop_trace_never_leaks_role_id_or_reward_payload(self):
        from wlre.network.non_npc_diagnostics import coop_state_trace
        state,_=ready()
        state.player['name']='PRIVATE-PLAYER'
        state.apply(members(23))
        state.apply(reward())
        trace=coop_state_trace(state,'instance_reward_status')
        self.assertTrue(trace['reward_known'])
        self.assertEqual(trace['open_reward'],1)
        self.assertNotIn('PRIVATE-PLAYER',str(trace))
        self.assertNotIn('678',str(trace))
        self.assertNotIn('23',str(trace))
        self.assertIsNone(coop_state_trace(state,'PRIVATE-COMMAND'))

    def test_maintenance_trace_contains_bounded_flags_only(self):
        from wlre.network.non_npc_diagnostics import maintenance_trace_event
        state,logic=ready()
        state.maintenance['status']='PRIVATE-ITEM'
        logic.maintenance.pending={'action':'repair','due':10,'private':'PRIVATE-ITEM'}
        trace=maintenance_trace_event(state,logic,10)
        self.assertEqual(trace['action'],'repair')
        self.assertEqual(trace['phase'],'pending')
        self.assertNotIn('PRIVATE-ITEM',str(trace))
        logic.maintenance.pending['action']='PRIVATE-NAME'
        self.assertEqual(maintenance_trace_event(state,logic,20)['action'],'none')

    def test_disconnect_while_pending_preserves_uncertainty(self):
        state,logic=ready();logic.world_acknowledged=True
        state.instances['coop']['join_pending']={'room_id':23,'started':1}
        logic.disconnect(state)
        self.assertTrue(state.instances['coop']['join_uncertain'])
        self.assertIsNone(state.instances['coop']['join_pending'])


if __name__=='__main__':
    unittest.main()
