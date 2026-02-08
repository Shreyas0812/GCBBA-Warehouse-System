"""
AgentState: 

Class to manage the execution state of an agent seperately from GCBBA logic
task lifecycle: planned -> executing -> completed
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from enum import Enum
from dataclasses import dataclass

class TaskState(Enum):
    PLANNED = "planned"
    EXECUTING = "executing"
    COMPLETED = "completed"

