import os, rods_pipeline as p
r = p.fetch(p.EP['matchups'], os.environ[d0e61cc38b113d902f042594d29c], tour='pga', market='tournament_matchups', odds_format='american')
print(r)
