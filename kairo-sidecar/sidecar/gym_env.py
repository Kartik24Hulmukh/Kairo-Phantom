"""
gym_env.py — Gymnasium environment wrapper for Kairo Phantom document tasks.

Structures document-editing episodes for reinforcement-learning workflows.

Action space (Discrete 3):
  0  Accept suggestion        → reward +1.0  (PASS)
  1  Request regeneration     → reward -0.1  (soft correction)
  2  Trigger CUA correction   → reward -0.5  (tool edit)

Fix-loop rewards (from TestFixLoop terminal states):
  PASS       → +1.0
  QUARANTINE → -1.0
  ESCALATE   → -2.0
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("kairo.gym_env")

try:
    import gymnasium as gym
    from gymnasium import spaces

    HAS_GYMNASIUM = True
except ImportError:

    class gym:  # type: ignore[no-redef]
        class Env:
            pass

    class spaces:  # type: ignore[no-redef]
        class Box:
            def __init__(self, *a, **kw):
                pass

        class Discrete:
            def __init__(self, n):
                self.n = n

        class Dict:
            def __init__(self, d):
                self.spaces = d

    HAS_GYMNASIUM = False


class KairoDocEnv(gym.Env):
    """
    Gymnasium environment representing a document-editing scenario.

    Uses DuckDB OutcomeStore (via the migrated outcome_store.py) to persist
    every step, and integrates with TestFixLoop for multi-step repair episodes.
    """

    # Fix-loop terminal-state → reward mapping
    FIX_LOOP_REWARDS = {
        "PASS": 1.0,
        "QUARANTINE": -1.0,
        "ESCALATE": -2.0,
    }

    def __init__(
        self,
        scenario_data: Dict[str, Any],
        outcome_store_path: Optional[str] = None,
    ):
        super().__init__()
        self.scenario = scenario_data
        self.state: Dict[str, Any] = {}

        if HAS_GYMNASIUM:
            self.action_space = spaces.Discrete(3)
            self.observation_space = spaces.Dict(
                {
                    "text_length": spaces.Discrete(100_000),
                    "relevance_score": spaces.Box(low=0.0, high=1.0, shape=(1,)),
                    "turns_count": spaces.Discrete(100),
                }
            )
        else:
            self.action_space = spaces.Discrete(3)
            self.observation_space = None

        from sidecar.outcome_store import OutcomeStore

        self.store = OutcomeStore(outcome_store_path)
        self.current_step = 0
        self.max_steps = scenario_data.get("fix_budget", 5)

    # ── Gymnasium API ─────────────────────────────────────────────────────────

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """Reset for a new episode."""
        self.current_step = 0
        self.state = {
            "text_length": len(self.scenario.get("prompt", "")),
            "relevance_score": 1.0,
            "turns_count": 0,
        }
        info = {
            "status": "initialized",
            "scenario_id": self.scenario.get("id"),
        }
        return self.state, info

    def step(self, action: int) -> Tuple[Dict[str, Any], float, bool, bool, Dict[str, Any]]:
        """
        Execute one step.

        Returns: observation, reward, terminated, truncated, info
        """
        self.current_step += 1
        terminated = False
        truncated = self.current_step >= self.max_steps

        if action == 0:  # Accept
            reward = 1.0
            terminated = True
            outcome_str = "ACCEPTED"
        elif action == 1:  # Regenerate
            reward = -0.1
            self.state["turns_count"] += 1
            outcome_str = "REGENERATE"
        elif action == 2:  # CUA correction
            reward = -0.5
            self.state["turns_count"] += 1
            outcome_str = "CUA_EDIT"
        else:
            reward = -2.0
            terminated = True
            outcome_str = "INVALID_ACTION"

        self.store.log_episode(
            scenario_id=self.scenario.get("id", "unknown"),
            state=self.state,
            intent=self.scenario.get("category", "test"),
            action=str(action),
            outcome=outcome_str,
            accepted=(outcome_str == "ACCEPTED"),
        )

        info = {
            "step": self.current_step,
            "outcome": outcome_str,
            "success": outcome_str == "ACCEPTED",
        }
        return self.state, reward, terminated, truncated, info

    # ── Fix-loop episode helper ───────────────────────────────────────────────

    def run_fix_loop_episode(
        self,
        fix_loop: Any,  # TestFixLoop instance
        initial_fail_result: Dict[str, Any],
        run_tests_fn,
        generate_fix_fn,
        apply_patch_fn,
        rollback_fn,
    ) -> Any:  # LoopResult
        """
        Run a complete TestFixLoop episode and log the structured LoopResult
        to DuckDB.  Returns the LoopResult dataclass.
        """
        result = fix_loop.run_loop(
            scenario_id=self.scenario.get("id", "unknown"),
            initial_fail_result=initial_fail_result,
            run_tests_fn=run_tests_fn,
            generate_fix_fn=generate_fix_fn,
            apply_patch_fn=apply_patch_fn,
            rollback_fn=rollback_fn,
            log_to_store=True,  # OutcomeStore.log_loop_result called inside loop
        )
        # Map terminal state to gym reward for interoperability
        gym_reward = self.FIX_LOOP_REWARDS.get(result.terminal_state, -1.0)
        log.info(
            f"[KairoDocEnv] fix_loop_episode done: "
            f"state={result.terminal_state} gym_reward={gym_reward:+.1f}"
        )
        return result
