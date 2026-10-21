"""Anonymous v0.5.12 non-NPC service traces for Android network worker.

No account, room ID, raw packet, role ID, free-form command or chat string.
"""
COOP_TRACE_SOURCES=frozenset((
    'instance_members', 'instance_phase', 'instance_reward_status',
    'instance_reward_receipt', 'instance_standby', 'instance_coop_match',
    'battle_start', 'fight_exit', 'battle_unit_exit', 'event_end',
))

def coop_state_trace(state,source):
    if source not in COOP_TRACE_SOURCES:
        return None
    coop=state.instances['coop']
    reward=coop.get('reward')
    room=coop.get('room')
    phase=coop.get('phase')
    if phase not in ('idle','waiting','started','matched','combat','completed'):
        phase='unknown'
    post=(state.battle.get('post_event') or {}).get('status','none')
    if post not in ('none','cooperative_wait','exit_delay',
                    'awaiting_response','completed'):
        post='unknown'
    open_reward=reward.get('open_reward') if isinstance(reward,dict) else None
    if type(open_reward) is not int or open_reward not in (0,1,2):
        open_reward=None
    standby=room.get('standby') if isinstance(room,dict) else None
    if type(standby) is not bool:
        standby=None
    pending=any(coop.get(key) is not None for key in (
        'create_pending','join_pending','leave_pending','standby_pending',
        'start_pending','enter_pending','claim_pending','cancel_pending'))
    return {'type':'coop_state_trace','source':source,'phase':phase,
            'room_known':isinstance(room,dict),'standby':standby,
            'reward_known':isinstance(reward,dict),'open_reward':open_reward,
            'completed':coop.get('completed') is True,
            'reward_uncertain':bool(coop.get('reward_uncertain')),
            'pending':pending,'event_blocked':bool(state.event_flow.get('blocked')),
            'post_event':post,'battle_count':state.battle_count}

def post_battle_trace(state,phase):
    event=state.battle.get('post_event') or {}
    delay=event.get('delay_seconds')
    count=state.instances.get('coop',{}).get('fight_count')
    return {'type':'post_battle_trace','phase':phase,
            'battle_count':state.battle_count,
            'war_style':state.battle.get('war_style'),
            'delay_seconds':delay,
            'fight_count_known':type(count) is int and count>=0}

def maintenance_trace_event(state,logic,now):
    guard=logic.maintenance
    pending=guard.pending
    phase=('uncertain' if guard.uncertain else 'pending' if pending
           else 'checking' if state.maintenance.get('checking') else 'idle')
    action=pending.get('action') if pending else 'none'
    if action not in ('repair','sell','delete'):
        action='none'
    elapsed=0
    if pending and type(pending.get('due')) in (int,float):
        elapsed=max(0,min(3600,int(now-(pending['due']-guard.timeout))))
    return {'type':'maintenance_trace','phase':phase,'action':action,
            'elapsed_s':elapsed,'battle_count':state.battle_count,
            'completed':state.maintenance.get('completed',0)}
