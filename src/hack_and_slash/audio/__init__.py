"""Sound: what the game plays, and what plays it.

Split in two on exactly the line `render/` is split on. `cues.py` decides *what*
should be heard and imports no pygame, so the decision is testable headlessly and
provably cannot reach a fight. `bank.py` owns the mixer and the files.
"""
