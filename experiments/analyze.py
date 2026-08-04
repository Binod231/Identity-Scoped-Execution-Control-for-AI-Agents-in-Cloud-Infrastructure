"""
ScopeGuard Experiment Analysis & Chart Generator.

Loads experiment results from CSV, calculates precision, recall, F1,
block rate, false positive rate, attribution metrics, and generates
visualizations for paper/presentation.
"""

import logging
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scopeguard.analyze")

plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")


class ExperimentAnalyzer:
    """Calculates statistics and creates publication-grade plots."""

    def __init__(self, results_csv: str = "experiments/results/ablation_results.csv"):
        self.csv_path = Path(results_csv)
        self.output_dir = self.csv_path.parent

    def load_data(self) -> pd.DataFrame:
        """Load experiment CSV data."""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Results CSV not found at {self.csv_path}. Run experiments.runner first.")
        return pd.read_csv(self.csv_path)

    def analyze_metrics(self, df: pd.DataFrame) -> dict:
        """Compute metrics for each ablation mode."""
        modes = df["mode"].unique()
        metrics_by_mode = {}

        for mode in modes:
            m_df = df[df["mode"] == mode]

            # Legitimate tasks (ground truth: ALLOWED)
            legit = m_df[~m_df["is_adversarial"]]
            fp = (legit["decision"] == "BLOCKED").sum()
            tn = (legit["decision"] == "ALLOWED").sum()

            # Adversarial tasks (ground truth: BLOCKED)
            adv = m_df[m_df["is_adversarial"]]
            tp = (adv["decision"] == "BLOCKED").sum()
            fn = (adv["decision"] == "ALLOWED").sum()

            total = len(m_df)
            accuracy = (tp + tn) / total if total > 0 else 0
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0

            block_rate_adv = (tp / len(adv)) * 100 if len(adv) > 0 else 0
            fpr_legit = (fp / len(legit)) * 100 if len(legit) > 0 else 0
            avg_latency = m_df["latency_ms"].mean()

            metrics_by_mode[mode] = {
                "total_calls": total,
                "TP": int(tp),
                "TN": int(tn),
                "FP": int(fp),
                "FN": int(fn),
                "Accuracy": round(accuracy, 4),
                "Precision": round(precision, 4),
                "Recall": round(recall, 4),
                "F1": round(f1, 4),
                "BlockRateAdvPct": round(block_rate_adv, 2),
                "FPRLegitPct": round(fpr_legit, 2),
                "AvgLatencyMs": round(avg_latency, 2),
            }

        return metrics_by_mode

    def plot_charts(self, df: pd.DataFrame, metrics: dict):
        """Generate charts for publication."""
        # 1. Block Rate vs False Positive Rate by Ablation Mode
        fig, ax = plt.subplots(figsize=(8, 5))
        modes = list(metrics.keys())
        block_rates = [metrics[m]["BlockRateAdvPct"] for m in modes]
        fpr_rates = [metrics[m]["FPRLegitPct"] for m in modes]

        x = np.arange(len(modes))
        width = 0.35

        ax.bar(x - width / 2, block_rates, width, label="Adversarial Block Rate (%)", color="#d9534f")
        ax.bar(x + width / 2, fpr_rates, width, label="Legitimate False Positive Rate (%)", color="#0275d8")

        ax.set_ylabel("Percentage (%)")
        ax.set_title("ScopeGuard Security & Accuracy across Ablation Modes")
        ax.set_xticks(x)
        ax.set_xticklabels([m.upper() for m in modes])
        ax.set_ylim(0, 110)
        ax.legend()

        for i in range(len(modes)):
            ax.text(x[i] - width / 2, block_rates[i] + 2, f"{block_rates[i]}%", ha="center", fontsize=9)
            ax.text(x[i] + width / 2, fpr_rates[i] + 2, f"{fpr_rates[i]}%", ha="center", fontsize=9)

        plt.tight_layout()
        plt.savefig(self.output_dir / "ablation_performance.png", dpi=300)
        plt.close()

        # 2. Latency Overhead Boxplot
        plt.figure(figsize=(8, 5))
        sns.boxplot(data=df, x="mode", y="latency_ms", palette="Blues")
        plt.axhline(y=200, color="r", linestyle="--", label="NFR1 Max Latency (200ms)")
        plt.ylabel("Latency Overhead (ms)")
        plt.title("Latency Distribution Across Ablation Modes")
        plt.legend()
        plt.tight_layout()
        plt.savefig(self.output_dir / "latency_overhead.png", dpi=300)
        plt.close()

        # 3. Confusion Matrix Heatmap for FULL Mode
        full_m = metrics.get("full", {})
        if full_m:
            cm = np.array([[full_m["TN"], full_m["FP"]], [full_m["FN"], full_m["TP"]]])
            plt.figure(figsize=(6, 5))
            sns.heatmap(cm, annot=True, fmt="d", cmap="Greens",
                        xticklabels=["Allowed", "Blocked"],
                        yticklabels=["Legitimate", "Adversarial"])
            plt.ylabel("True Class")
            plt.xlabel("Predicted Decision")
            plt.title("Confusion Matrix — Full ScopeGuard Scoping Mode")
            plt.tight_layout()
            plt.savefig(self.output_dir / "confusion_matrix_full.png", dpi=300)
            plt.close()

        logger.info("Saved all visual charts to %s", self.output_dir)

    def run(self):
        """Perform full analysis and output report."""
        df = self.load_data()
        metrics = self.analyze_metrics(df)

        print("\n" + "=" * 65)
        print("           SCOPEGUARD EXPERIMENT METRICS SUMMARY           ")
        print("=" * 65)
        metrics_df = pd.DataFrame(metrics).T
        print(metrics_df[["Accuracy", "Precision", "Recall", "F1", "BlockRateAdvPct", "FPRLegitPct", "AvgLatencyMs"]])
        print("=" * 65 + "\n")

        self.plot_charts(df, metrics)


if __name__ == "__main__":
    analyzer = ExperimentAnalyzer()
    analyzer.run()
