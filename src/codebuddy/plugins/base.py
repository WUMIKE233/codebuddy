"""Plugin system — abstract base for language-specific extensions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ScannerRule:
    """Rule for classifying files in the Scanner Agent."""
    name: str
    file_patterns: list[str] = field(default_factory=list)


@dataclass
class AnalyzerCheck:
    """A static analysis check for the Analyzer Agent."""
    name: str
    description: str
    category: str  # bug, smell, security, performance, style
    severity: str  # critical, high, medium, low, info


@dataclass
class RefactoringPattern:
    """A refactoring pattern for the Refactorer Agent."""
    name: str
    description: str
    applicable_languages: list[str] = field(default_factory=list)
    prompt_hint: str = ""


class PluginBase(ABC):
    """Abstract plugin interface. Third-party plugins subclass this."""

    name: str = ""
    languages: list[str] = []
    version: str = "0.1.0"

    @abstractmethod
    def get_scanner_rules(self) -> list[ScannerRule]:
        """Rules for file classification during scanning."""
        ...

    @abstractmethod
    def get_analyzer_checks(self) -> list[AnalyzerCheck]:
        """Static analysis checks for the Analyzer Agent."""
        ...

    @abstractmethod
    def get_refactoring_patterns(self) -> list[RefactoringPattern]:
        """Refactoring patterns for the Refactorer Agent."""
        ...
