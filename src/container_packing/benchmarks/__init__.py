"""Reproducible algorithm benchmark orchestration."""

from .analysis import BenchmarkAnalysis, analyze_benchmark
from .catalog import BenchmarkCatalog, BenchmarkCatalogEntry, load_benchmark_catalog
from .corpus import BenchmarkCorpusResult, load_benchmark_corpus, run_benchmark_corpus
from .canonical_evidence import (
    build_canonical_benchmark_evidence,
    write_canonical_benchmark_evidence,
)
from .constructor_portfolio_acceptance import (
    evaluate_constructor_portfolio_acceptance,
    write_constructor_portfolio_acceptance,
)
from .runner import BenchmarkResult, run_benchmark
from .repair_acceptance import (
    evaluate_level3_repair_acceptance,
    write_level3_repair_acceptance,
)
from .suites import BenchmarkScenario, BenchmarkSuite, load_benchmark_suite

__all__ = [
    "BenchmarkAnalysis",
    "BenchmarkCatalog",
    "BenchmarkCatalogEntry",
    "BenchmarkCorpusResult",
    "BenchmarkResult",
    "BenchmarkScenario",
    "BenchmarkSuite",
    "analyze_benchmark",
    "build_canonical_benchmark_evidence",
    "evaluate_level3_repair_acceptance",
    "evaluate_constructor_portfolio_acceptance",
    "load_benchmark_corpus",
    "load_benchmark_catalog",
    "load_benchmark_suite",
    "run_benchmark",
    "run_benchmark_corpus",
    "write_level3_repair_acceptance",
    "write_constructor_portfolio_acceptance",
    "write_canonical_benchmark_evidence",
]
