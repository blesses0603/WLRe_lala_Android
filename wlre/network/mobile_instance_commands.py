"""Android-specific routing of verified desktop v0.5.12 instance and allocation actions.

No NPC commands. All mutations are performed only on the network worker
following the existing IPC allowlist and server-confirmation safety guards.
"""
from wlre.network.wire import ProtocolError
from wlre.services.instance_creation import create
from wlre.services.instance_room_flow import join, leave
from wlre.services.instance_standby import set_standby
from wlre.services.instance_start import start
from wlre.services.instance_entry import enter
from wlre.services.instance_rewards import set_auto, claim, cancel
from wlre.services.battle.attribute_points import allocation, begin

_HANDLERS={
    'instance_create':create,
    'instance_join':join,
    'instance_leave':leave,
    'instance_coop_standby':set_standby,
    'instance_start':start,
    'instance_enter':enter,
    'instance_auto_reward':set_auto,
    'instance_reward_claim':claim,
    'instance_reward_cancel':cancel,
}

def dispatch(state,command):
    kind=command.get('type')
    if kind=='allocate_points':
        if (state.phase!='world_ready' or not state.initial_data_complete
                or not state.player.get('role_id')):
            raise ProtocolError('請等待角色與世界資料同步')
        if (state.battle.get('active') or state.event_flow.get('blocked')
                or state.roaming.get('enabled')):
            raise ProtocolError('戰鬥、事件或移動中不可配點')
        player=state.knowledge.get('player') or {}
        if not player.get('ready'):
            raise ProtocolError('角色能力尚未同步')
        if state.attribute_allocation.get('pending') or state.attribute_allocation.get('uncertain'):
            raise ProtocolError('配點結果未確認，請重新同步')
        packet,expected=allocation(player['stats'],command.get('increments'),
                                   command.get('baseline'))
        begin(state,expected)
        return [packet]
    handler=_HANDLERS.get(kind)
    if handler is None:
        raise ProtocolError('不支援的副本指令')
    return handler(state,command)
