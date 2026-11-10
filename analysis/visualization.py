"""Static scientific charts for validated CPU scaling results."""

from pathlib import Path


def load_plotting():
    """Use a headless backend so charts can be generated on benchmark hosts."""
    try:
        import matplotlib
    except ImportError as error:
        raise ImportError(
            "Charts require matplotlib. Install with: python3 -m pip install -r analysis/requirement-analysis.txt"
        ) from error
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def plot_results(summary: list[dict], details: dict, output: Path) -> None:
    """Write a four-panel PNG and PDF using the same samples as the summary."""
    plt = load_plotting()
    workers = [row["workers"] for row in summary]
    positions = list(range(len(workers)))
    medians = [row["median_s"] for row in summary]
    samples = [details["samples"][count] for count in workers]
    baseline = details["baseline_workers"]
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False}):
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
        try:
            ax = axes[0, 0]
            ax.errorbar(
                positions, medians,
                yerr=[
                    [row["median_s"] - row["min_s"] for row in summary],
                    [row["max_s"] - row["median_s"] for row in summary],
                ],
                fmt="o-", capsize=5, color="#2563eb", label="Median; whiskers = min–max",
            )
            ax.set(title="Execution time", ylabel="Time (seconds)")
            ax.set_ylim(bottom=0)
            ax.legend(fontsize=9)

            ax = axes[0, 1]
            ax.plot(positions, [row["speedup"] for row in summary], "o-", color="#2563eb", label="Observed")
            ax.plot(positions, [count / baseline for count in workers], "--", color="#64748b", label="Ideal linear scaling")
            ax.set(title=f"Speedup relative to {baseline} worker(s)", ylabel="Speedup (×)")
            ax.set_ylim(bottom=0)
            ax.legend(fontsize=9)

            ax = axes[1, 0]
            ax.plot(positions, [row["relative_efficiency_percent"] for row in summary], "o-", color="#0f766e")
            ax.axhline(100, linestyle="--", color="#64748b", label="Ideal: 100%")
            ax.set(title="Relative parallel efficiency", ylabel="Efficiency (%)")
            ax.set_ylim(bottom=0)
            ax.legend(fontsize=9)

            ax = axes[1, 1]
            ax.boxplot(samples, positions=positions, widths=0.45, showfliers=False)
            for position, values in zip(positions, samples):
                # Deterministic offsets keep repeated timings visible.
                offsets = [0 if len(values) == 1 else (index / (len(values) - 1) - 0.5) * 0.24 for index in range(len(values))]
                ax.scatter([position + offset for offset in offsets], values, s=18, alpha=0.65, color="#2563eb")
            ax.set(title="Measured timing distribution (all samples shown)", ylabel="Time (seconds)")
            ax.set_ylim(bottom=0)

            for ax in axes.flat:
                ax.set_xticks(positions, [str(count) for count in workers])
                ax.set_xlabel("Workers")
                ax.grid(axis="y", alpha=0.2)
            fig.suptitle(
                f"CPU scaling · {details['iterations']:,} total iterations · {details['timing']}\n"
                f"Successful measured runs only · n per worker: {', '.join(str(row['runs']) for row in summary)}",
                fontsize=13,
            )
            fig.savefig(output / "scaling.png", dpi=180)
            fig.savefig(output / "scaling.pdf")
        finally:
            plt.close(fig)
