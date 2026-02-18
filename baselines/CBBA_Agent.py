"""
CBBA Agent class for Warehouse Task Allocation.

Standard CBBA (Choi et al. 2009) baseline:
- FULLBUNDLE bundle building: fills entire bundle in a while loop before consensus
- Same consensus/conflict resolution as GCBBA
- No convergence detection
"""

from gcbba.GCBBA_Agent import GCBBA_Agent

class CBBA_Agent(GCBBA_Agent):
    """
    Same functoins as GCBBA_Agent but overrides create_bundle() to use FULLBUNDLE strategy.
        - GCBBA (ADD): adds ONE task per create_bundle() call, then 2D consensus rounds
        - CBBA (FULLBUNDLE): adds ALL tasks up to capacity in one create_bundle() call, 
        then 1 consensus round

    Similarly in resolve_conflicts(), CBBA only does 1 round of conflict resolution after bundle building, no convergence detection.
    
    Other functionality remaints the same
    """