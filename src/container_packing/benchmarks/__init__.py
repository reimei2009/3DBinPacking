"""Reproducible algorithm benchmark orchestration."""

from .analysis import BenchmarkAnalysis, analyze_benchmark
from .catalog import BenchmarkCatalog, BenchmarkCatalogEntry, load_benchmark_catalog
from .corpus import BenchmarkCorpusResult, load_benchmark_corpus, run_benchmark_corpus
from .canonical_evidence import (
    build_canonical_benchmark_evidence,
    write_canonical_benchmark_evidence,
)
from .runner import BenchmarkResult, run_benchmark
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
    "load_benchmark_corpus",
    "load_benchmark_catalog",
    "load_benchmark_suite",
    "run_benchmark",
    "run_benchmark_corpus",
    "write_canonical_benchmark_evidence",
]
