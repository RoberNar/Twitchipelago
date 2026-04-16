import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from database import init_db, get_config_as_json, save_config_from_json, get_or_create_user, log_event, get_channel_stats

init_db()
print('OK: init_db')

user = get_or_create_user('123456', 'RyuguuDK', 'https://x.com/a.jpg', 'tok', 'ref')
print('OK: create_user id=' + str(user.id) + ' name=' + user.display_name)

cfg = get_config_as_json(user_id=user.id)
print('OK: get_config players=' + str(len(cfg['players'])) + ' rewards=' + str(len(cfg['rewards'])))

patch = dict(cfg)
patch['archipelago']['port'] = 99999
save_config_from_json(patch, user_id=user.id)
cfg2 = get_config_as_json(user_id=user.id)
assert cfg2['archipelago']['port'] == 99999, 'port no guardado'
print('OK: save_config port=99999')

log_event('ryuguudk', 'bits', amount=200, user_name='viewer')
log_event('ryuguudk', 'hint_triggered', user_name='viewer', reward_id='hint_random')
stats = get_channel_stats('ryuguudk')
assert stats['total_bits'] == 200, 'bits incorrectos'
assert stats['total_hints_triggered'] == 1, 'hints incorrectos'
print('OK: event_log bits=' + str(stats['total_bits']) + ' hints=' + str(stats['total_hints_triggered']))

print('')
print('FASE 2 VERIFICADA OK')
