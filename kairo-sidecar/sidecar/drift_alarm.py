import logging
import json
import os
import datetime
from typing import Dict, Any, List, Optional
import duckdb

log = logging.getLogger("kairo.drift_alarm")


class DriftAlarm:
    """Monitors evaluation drift and protects the learning loop from training on wrong assumptions."""

    def __init__(self, threshold: float = 0.05):
        self.threshold = threshold
        self.drift_history: List[float] = []
        self.training_frozen = self._load_freeze_state()

    def _load_freeze_state(self) -> bool:
        sidecar_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        state_path = os.path.join(sidecar_dir, "training_state.json")
        if os.path.exists(state_path):
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return bool(data.get("training_frozen", False))
            except Exception as e:
                log.error(f"[Drift Alarm] Failed to read training_state.json: {e}")
        return False

    def _save_freeze_state(self, frozen: bool):
        sidecar_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        state_path = os.path.join(sidecar_dir, "training_state.json")
        try:
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump({"training_frozen": frozen}, f, indent=2)
        except Exception as e:
            log.error(f"[Drift Alarm] Failed to write training_state.json: {e}")

    def check_drift(
        self,
        synthetic_results: List[Dict[str, Any]],
        human_labels: Optional[Dict[str, bool]] = None,
    ) -> float:
        """
        Compute drift gap: |synthetic_pass_rate - human_pass_rate| on the calibration set.
        If gap > threshold, freeze training and persist metrics to DuckDB.
        """
        if not human_labels:
            # Load calibration_set.json
            sidecar_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            calibration_path = os.path.join(sidecar_dir, "calibration_set.json")
            if os.path.exists(calibration_path):
                try:
                    with open(calibration_path, "r", encoding="utf-8") as f:
                        human_labels = json.load(f)
                except Exception as e:
                    log.error(f"[Drift Alarm] Failed to load calibration set: {e}")
                    human_labels = {}
            else:
                human_labels = {}

        if not synthetic_results or not human_labels:
            log.warning("[Drift Alarm] Empty calibration data. Skipping drift check.")
            return 0.0

        # Calculate synthetic pass rate on overlap
        syn_count = 0
        syn_passes = 0
        overlap_ids = []
        for res in synthetic_results:
            scenario_id = res.get("scenario_id")
            if scenario_id in human_labels:
                syn_count += 1
                overlap_ids.append(scenario_id)
                if res.get("passed", False):
                    syn_passes += 1

        if syn_count == 0:
            log.warning(
                "[Drift Alarm] No overlapping calibration scenarios found between synthetic and human sets."
            )
            return 0.0

        synthetic_pass_rate = syn_passes / syn_count

        # Calculate human pass rate on overlap
        human_passes = sum(1 for sid in overlap_ids if human_labels[sid])
        human_pass_rate = human_passes / len(overlap_ids)

        # Drift gap
        drift_gap = abs(synthetic_pass_rate - human_pass_rate)
        self.drift_history.append(drift_gap)

        log.info(
            f"[Drift Alarm] Synthetic pass rate: {synthetic_pass_rate:.3f} | Human pass rate: {human_pass_rate:.3f} | Drift gap: {drift_gap:.3f}"
        )

        if drift_gap > self.threshold:
            self.trigger_freeze(drift_gap)
        else:
            self.training_frozen = False
            self._save_freeze_state(False)
            log.info("[Drift Alarm] Calibration drift is within acceptable bounds.")

        # Persist drift history metrics to DuckDB
        try:
            repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_dir = os.path.join(repo_root, "target")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "gauntlet_outcomes.duckdb")

            con = duckdb.connect(db_path)
            try:
                con.execute("CREATE SEQUENCE IF NOT EXISTS drift_metrics_id_seq")
                con.execute("""
                    CREATE TABLE IF NOT EXISTS drift_metrics (
                        id INTEGER DEFAULT nextval('drift_metrics_id_seq'),
                        synthetic_pass_rate DOUBLE,
                        human_pass_rate DOUBLE,
                        drift_gap DOUBLE,
                        threshold DOUBLE,
                        frozen BOOLEAN,
                        timestamp TIMESTAMP
                    )
                """)
                con.execute(
                    """
                    INSERT INTO drift_metrics (synthetic_pass_rate, human_pass_rate, drift_gap, threshold, frozen, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    [
                        float(synthetic_pass_rate),
                        float(human_pass_rate),
                        float(drift_gap),
                        float(self.threshold),
                        bool(self.training_frozen),
                        datetime.datetime.utcnow(),
                    ],
                )
            finally:
                con.close()
        except Exception as e:
            log.error(f"[Drift Alarm] Failed to persist drift metrics to DuckDB: {e}")

        return drift_gap

    def trigger_freeze(self, gap: float):
        """Freeze training to prevent bad reinforcement learning loops."""
        self.training_frozen = True
        self._save_freeze_state(True)
        log.critical(
            f"🚨 [DRIFT ALARM] TRAINING FROZEN! "
            f"Drift gap {gap:.3f} exceeded safety threshold of {self.threshold:.3f}. "
            f"Please recalibrate AI judges and update user population!"
        )

    def is_frozen(self) -> bool:
        """Check if training is currently frozen."""
        return self.training_frozen
