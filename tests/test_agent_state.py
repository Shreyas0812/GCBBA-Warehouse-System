"""
Test Suite for AgentState Class

Validates core functionality:
1. Initialization and basic state
2. Task lifecycle management (planned → executing → completed)
3. Path assignment and following
4. Position prediction
5. GCBBA integration updates
6. Edge cases and error handling

Author: Shreyas
Date: February 2026
"""

import pytest
import numpy as np
from integration.agent_state import AgentState, TaskState


# ============================================================================
# TEST SECTION 1: Initialization
# ============================================================================

class TestInitialization:
    """Test AgentState initialization and basic properties"""
    
    def test_basic_initialization(self):
        """Test that agent initializes with correct default state"""
        agent = AgentState(agent_id=0, initial_position=(5, 10, 0), speed=1.0)
        
        assert agent.agent_id == 0
        assert np.array_equal(agent.pos, [5.0, 10.0, 0.0])
        assert agent.speed == 1.0
        assert agent.is_idle == True
        assert agent.is_stuck == False
        assert len(agent.planned_tasks) == 0
        assert agent.current_task is None
        assert len(agent.completed_tasks) == 0
        assert agent.current_timestep == 0
        
        print("✓ Basic initialization test passed")
    
    def test_position_history(self):
        """Test that initial position is recorded in history"""
        agent = AgentState(agent_id=1, initial_position=(3, 7, 0), speed=1.5)
        
        assert len(agent.position_history) == 1
        assert agent.position_history[0] == (3.0, 7.0, 0.0, 0)
        
        print("✓ Position history initialization passed")


# ============================================================================
# TEST SECTION 2: GCBBA Integration
# ============================================================================

class TestGCBBAIntegration:
    """Test updating agent state from GCBBA allocation"""
    
    def test_update_from_empty_gcbba(self):
        """Test updating with no tasks allocated"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        agent.update_from_gcbba(assigned_tasks=[], current_timestep=10)
        
        assert len(agent.planned_tasks) == 0
        assert agent.is_idle == True
        assert agent.current_timestep == 10
        
        print("✓ Empty GCBBA update test passed")
    
    def test_update_single_task(self):
        """Test updating with single task from GCBBA"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        tasks = [
            {'task_id': 5, 'induct_pos': [2, 3], 'eject_pos': [8, 9]}
        ]
        
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        assert len(agent.planned_tasks) == 1
        assert agent.planned_tasks[0].task_id == 5
        assert agent.planned_tasks[0].induct_pos == (2, 3)
        assert agent.planned_tasks[0].eject_pos == (8, 9)
        assert agent.planned_tasks[0].state == TaskState.PLANNED
        assert agent.is_idle == False  # Should become busy when tasks assigned
        
        print("✓ Single task GCBBA update test passed")
    
    def test_update_multiple_tasks(self):
        """Test updating with multiple tasks from GCBBA"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        tasks = [
            {'task_id': 1, 'induct_pos': [1, 1], 'eject_pos': [5, 5]},
            {'task_id': 2, 'induct_pos': [2, 2], 'eject_pos': [6, 6]},
            {'task_id': 3, 'induct_pos': [3, 3], 'eject_pos': [7, 7]},
        ]
        
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=5)
        
        assert len(agent.planned_tasks) == 3
        assert [t.task_id for t in agent.planned_tasks] == [1, 2, 3]
        assert all(t.state == TaskState.PLANNED for t in agent.planned_tasks)
        
        print("✓ Multiple task GCBBA update test passed")
    
    def test_update_replaces_planned_tasks(self):
        """Test that new GCBBA allocation replaces old planned tasks"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        # First allocation
        tasks1 = [
            {'task_id': 1, 'induct_pos': [1, 1], 'eject_pos': [5, 5]},
            {'task_id': 2, 'induct_pos': [2, 2], 'eject_pos': [6, 6]},
        ]
        agent.update_from_gcbba(assigned_tasks=tasks1, current_timestep=0)
        
        # Second allocation (different tasks)
        tasks2 = [
            {'task_id': 10, 'induct_pos': [10, 10], 'eject_pos': [15, 15]},
        ]
        agent.update_from_gcbba(assigned_tasks=tasks2, current_timestep=10)
        
        # Old tasks should be replaced
        assert len(agent.planned_tasks) == 1
        assert agent.planned_tasks[0].task_id == 10
        
        print("✓ Task replacement test passed")


# ============================================================================
# TEST SECTION 3: Path Assignment
# ============================================================================

class TestPathAssignment:
    """Test assigning collision-free paths to agents"""
    
    def test_assign_path_starts_task(self):
        """Test that assigning path moves first planned task to executing"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        # Give agent a task
        tasks = [{'task_id': 1, 'induct_pos': [5, 5], 'eject_pos': [10, 10]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        # Assign path
        path = [(0, 0, 0), (1, 1, 1), (2, 2, 2), (3, 3, 3), (5, 5, 4)]
        agent.assign_path(path)
        
        # Task should move from planned to executing
        assert len(agent.planned_tasks) == 0
        assert agent.current_task is not None
        assert agent.current_task.task_id == 1
        assert agent.current_task.state == TaskState.EXECUTING
        assert agent.current_task.path == path
        assert agent.current_path == path
        assert agent.current_path_index == 0
        
        print("✓ Path assignment starts task test passed")
    
    def test_assign_path_when_no_tasks(self):
        """Test assigning path when agent has no tasks (should do nothing)"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        path = [(0, 0, 0), (1, 1, 1)]
        agent.assign_path(path)
        
        # Should not create task or path
        assert agent.current_task is None
        assert agent.current_path is None
        
        print("✓ Path assignment with no tasks test passed")


# ============================================================================
# TEST SECTION 4: Motion Execution
# ============================================================================

class TestMotionExecution:
    """Test agent movement along paths"""
    
    def test_step_along_path(self):
        """Test agent follows path correctly over multiple timesteps"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        # Setup task and path
        tasks = [{'task_id': 1, 'induct_pos': [3, 3], 'eject_pos': [10, 10]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        path = [(0, 0, 0), (1, 1, 1), (2, 2, 2), (3, 3, 3)]
        agent.assign_path(path)
        
        # Execute steps
        completed = agent.step(timestep=1)
        assert not completed
        assert np.array_equal(agent.pos, [0, 0, 0])
        assert agent.current_path_index == 1
        
        completed = agent.step(timestep=2)
        assert not completed
        assert np.array_equal(agent.pos, [1, 1, 1])
        assert agent.current_path_index == 2
        
        completed = agent.step(timestep=3)
        assert not completed
        assert np.array_equal(agent.pos, [2, 2, 2])
        assert agent.current_path_index == 3
        
        # Last step completes induct phase, requires new path
        completed = agent.step(timestep=4)
        assert not completed
        assert np.array_equal(agent.pos, [3, 3, 3])
        assert agent.current_task is not None
        assert agent.task_phase == "to_eject"
        assert agent.needs_new_path == True

        # Assign path to eject station and complete task
        eject_path = [(4, 4, 4), (5, 5, 5)]
        agent.assign_path(eject_path)
        agent.step(timestep=5)
        completed = agent.step(timestep=6)
        assert completed
        assert np.array_equal(agent.pos, [5, 5, 5])
        assert agent.current_task is None
        assert len(agent.completed_tasks) == 1
        
        print("✓ Step along path test passed")
    
    def test_step_with_no_path(self):
        """Test stepping when agent has no path (stays in place)"""
        agent = AgentState(agent_id=0, initial_position=(5, 5, 0), speed=1.0)
        
        completed = agent.step(timestep=1)
        
        assert not completed
        assert np.array_equal(agent.pos, [5, 5, 0])
        assert len(agent.position_history) == 2  # Initial + step
        
        print("✓ Step with no path test passed")
    
    def test_task_completion(self):
        """Test that completing path marks task as completed"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        # Setup two tasks
        tasks = [
            {'task_id': 1, 'induct_pos': [2, 2], 'eject_pos': [5, 5]},
            {'task_id': 2, 'induct_pos': [4, 4], 'eject_pos': [8, 8]},
        ]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        # Assign and complete first task
        path1 = [(0, 0, 0), (1, 1, 1), (2, 2, 2)]
        agent.assign_path(path1)
        
        agent.step(1)  # Move to (0,0)
        agent.step(2)  # Move to (1,1)
        completed = agent.step(3)  # Move to (2,2) and finish induct phase

        assert not completed
        assert agent.task_phase == "to_eject"
        assert agent.needs_new_path == True

        # Complete to_eject phase
        path2 = [(3, 3, 3)]
        agent.assign_path(path2)
        completed = agent.step(4)

        assert completed
        assert len(agent.completed_tasks) == 1
        assert agent.completed_tasks[0].task_id == 1
        assert agent.completed_tasks[0].state == TaskState.COMPLETED
        assert agent.completed_tasks[0].completion_time == 4
        assert len(agent.planned_tasks) == 1  # Task 2 still planned
        assert agent.is_idle == False  # Still has planned tasks
        
        print("✓ Task completion test passed")
    
    def test_becomes_idle_after_all_tasks(self):
        """Test agent becomes idle after completing all tasks"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        # Single task
        tasks = [{'task_id': 1, 'induct_pos': [1, 1], 'eject_pos': [5, 5]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        path = [(0, 0, 0), (1, 1, 1)]
        agent.assign_path(path)
        
        agent.step(1)
        completed = agent.step(2)

        assert not completed
        assert agent.task_phase == "to_eject"
        assert agent.needs_new_path == True

        # Complete eject phase
        eject_path = [(2, 2, 2)]
        agent.assign_path(eject_path)
        completed = agent.step(3)

        assert completed
        assert agent.is_idle == True
        assert agent.current_task is None
        assert len(agent.planned_tasks) == 0
        
        print("✓ Becomes idle after all tasks test passed")


# ============================================================================
# TEST SECTION 5: Position Prediction
# ============================================================================

class TestPositionPrediction:
    """Test prediction of future agent positions"""
    
    def test_predict_with_no_path(self):
        """Prediction when agent has no path (stays at current position)"""
        agent = AgentState(agent_id=0, initial_position=(7, 12, 0), speed=1.0)
        
        predicted = agent.get_predicted_position(steps_ahead=5)
        
        assert predicted == (7, 12, 0)
        
        print("✓ Predict with no path test passed")
    
    def test_predict_during_execution(self):
        """Prediction during path execution"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        # Setup path
        tasks = [{'task_id': 1, 'induct_pos': [10, 10], 'eject_pos': [20, 20]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        path = [
            (0, 0, 0), (1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, 4),
            (5, 5, 5), (6, 6, 6), (7, 7, 7), (8, 8, 8), (10, 10, 9)
        ]
        agent.assign_path(path)
        
        # At start, predict 5 steps ahead
        predicted = agent.get_predicted_position(steps_ahead=5)
        assert predicted == (5, 5, 5)  # path[0 + 5]
        
        # After 3 steps, predict 5 ahead
        agent.step(1)
        agent.step(2)
        agent.step(3)
        
        predicted = agent.get_predicted_position(steps_ahead=5)
        assert predicted == (8, 8, 8)  # path[3 + 5]
        
        print("✓ Predict during execution test passed")
    
    def test_predict_beyond_path_end(self):
        """Prediction when steps_ahead goes past end of path"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        tasks = [{'task_id': 1, 'induct_pos': [3, 3], 'eject_pos': [5, 5]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        path = [(0, 0, 0), (1, 1, 1), (2, 2, 2), (3, 3, 3)]
        agent.assign_path(path)
        
        # Predict 100 steps ahead (past end of path)
        predicted = agent.get_predicted_position(steps_ahead=100)
        
        # Should return final position
        assert predicted == (3, 3, 3)
        
        print("✓ Predict beyond path end test passed")


# ============================================================================
# TEST SECTION 6: Goal Management
# ============================================================================

class TestGoalManagement:
    """Test getting current and next task goals"""
    
    def test_get_current_goal_executing(self):
        """Get goal when task is executing"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        tasks = [{'task_id': 1, 'induct_pos': [5, 10], 'eject_pos': [15, 20]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        path = [(0, 0, 0), (5, 10, 1)]
        agent.assign_path(path)
        
        goal = agent.get_current_goal()
        assert goal == (5, 10)
        
        print("✓ Get current goal (executing) test passed")
    
    def test_get_current_goal_planned(self):
        """Get goal when no task executing but tasks planned"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        tasks = [
            {'task_id': 1, 'induct_pos': [3, 7], 'eject_pos': [8, 12]},
            {'task_id': 2, 'induct_pos': [5, 5], 'eject_pos': [10, 10]},
        ]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        # No path assigned yet
        goal = agent.get_current_goal()
        assert goal == (3, 7)  # First planned task's induct
        
        print("✓ Get current goal (planned) test passed")
    
    def test_get_current_goal_idle(self):
        """Get goal when agent is idle"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        goal = agent.get_current_goal()
        assert goal is None
        
        print("✓ Get current goal (idle) test passed")
    
    def test_get_next_task_goal(self):
        """Get next task goal"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        tasks = [
            {'task_id': 1, 'induct_pos': [3, 3], 'eject_pos': [8, 8]},
            {'task_id': 2, 'induct_pos': [7, 7], 'eject_pos': [12, 12]},
        ]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        
        # Assign path to first task
        path = [(0, 0, 0), (3, 3, 1)]
        agent.assign_path(path)
        
        next_goal = agent.get_next_task_goal()
        assert next_goal == (7, 7)  # Second task's induct
        
        print("✓ Get next task goal test passed")


# ============================================================================
# TEST SECTION 7: Status and Utilities
# ============================================================================

class TestStatusUtilities:
    """Test status checking and summary methods"""
    
    def test_has_tasks(self):
        """Test has_tasks method"""
        agent = AgentState(agent_id=0, initial_position=(0, 0, 0), speed=1.0)
        
        # Initially no tasks
        assert agent.has_tasks() == False
        
        # Add planned tasks
        tasks = [{'task_id': 1, 'induct_pos': [2, 2], 'eject_pos': [5, 5]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=0)
        assert agent.has_tasks() == True
        
        # Start executing
        path = [(0, 0, 0), (2, 2, 1)]
        agent.assign_path(path)
        assert agent.has_tasks() == True
        
        # Complete induct phase (still has task)
        agent.step(1)
        agent.step(2)
        assert agent.has_tasks() == True

        # Complete eject phase
        eject_path = [(3, 3, 3)]
        agent.assign_path(eject_path)
        agent.step(3)
        assert agent.has_tasks() == False
        
        print("✓ Has tasks test passed")
    
    def test_get_status_summary(self):
        """Test status summary generation"""
        agent = AgentState(agent_id=5, initial_position=(3, 7, 0), speed=1.0)
        
        tasks = [{'task_id': 10, 'induct_pos': [5, 5], 'eject_pos': [10, 10]}]
        agent.update_from_gcbba(assigned_tasks=tasks, current_timestep=15)
        
        path = [(3, 7, 15), (5, 5, 16)]
        agent.assign_path(path)
        
        status = agent.get_status_summary()
        
        assert status['agent_id'] == 5
        assert status['position'] == (3.0, 7.0, 0.0)
        assert status['is_idle'] == False
        assert status['current_task'] == 10
        assert status['num_planned'] == 0
        assert status['num_completed'] == 0
        assert status['timestep'] == 15
        
        print("✓ Status summary test passed")
    
    def test_repr(self):
        """Test string representation"""
        agent = AgentState(agent_id=3, initial_position=(5, 10, 0), speed=1.0)
        
        repr_str = repr(agent)
        assert "Agent3" in repr_str
        assert "IDLE" in repr_str
        
        print(f"✓ Repr test passed: {repr_str}")


# ============================================================================
# Main execution
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("AgentState Test Suite")
    print("=" * 70)
    
    # Run all tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])