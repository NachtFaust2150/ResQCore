import math
import numpy as np

try:
    from sklearn.ensemble import RandomForestRegressor
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

class RiskPredictor:
    def __init__(self):
        self.model = None
        self.feature_names = ["dist_river", "elevation", "drainage", "rainfall"]
        self.feature_importances = {"dist_river": 0.35, "elevation": 0.25, "drainage": 0.20, "rainfall": 0.20}
        self.is_synthetic = True
        self._train_synthetic_model()

    def _train_synthetic_model(self):
        if not SKLEARN_AVAILABLE:
            return

        np.random.seed(42)
        n_samples = 200

        # Feature synthetic distributions
        dist_river = np.random.uniform(0.2, 5.0, n_samples)  # km
        elevation = np.random.uniform(850, 950, n_samples)   # meters
        drainage = np.random.uniform(0.1, 1.0, n_samples)    # index
        rainfall = np.random.uniform(5.0, 60.0, n_samples)   # mm

        X = np.column_stack([dist_river, elevation, drainage, rainfall])

        # Target risk formula with noise
        # Risk increases with lower dist_river, lower elevation, lower drainage, higher rainfall
        raw_risk = (
            (5.0 - dist_river) / 5.0 * 0.35 +
            (950 - elevation) / 100.0 * 0.20 +
            (1.0 - drainage) * 0.25 +
            (rainfall / 60.0) * 0.20 +
            np.random.normal(0, 0.05, n_samples)
        )
        y = np.clip(raw_risk, 0.0, 1.0)

        rf = RandomForestRegressor(n_estimators=50, random_state=42)
        rf.fit(X, y)
        self.model = rf

        # Store feature importances
        importances = rf.feature_importances_
        self.feature_importances = {
            name: float(round(imp, 4))
            for name, imp in zip(self.feature_names, importances)
        }

    def predict_risk(self, dist_river: float, elevation: float, drainage: float, rainfall: float) -> float:
        if self.model and SKLEARN_AVAILABLE:
            X = np.array([[dist_river, elevation, drainage, rainfall]])
            risk = float(self.model.predict(X)[0])
            return round(max(0.0, min(1.0, risk)), 3)
        else:
            # Fallback transparent sigmoidal risk calculation
            score = (5.0 - dist_river)*0.3 + (950 - elevation)*0.002 + (1.0 - drainage)*0.3 + (rainfall/60.0)*0.4
            sigmoid = 1.0 / (1.0 + math.exp(-(score - 0.8) * 3))
            return round(max(0.0, min(1.0, sigmoid)), 3)

    def get_risk_level(self, risk_score: float) -> str:
        if risk_score < 0.4:
            return "Low"
        elif risk_score < 0.66:
            return "Medium"
        else:
            return "High"

# Global singleton predictor
risk_predictor = RiskPredictor()
