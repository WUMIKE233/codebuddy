"""Plugin registry — discovery via Python entry points."""

from __future__ import annotations

from importlib.metadata import entry_points
from codebuddy.plugins.base import PluginBase, AnalyzerCheck, RefactoringPattern, ScannerRule


class PluginRegistry:
    """Discovers and loads CodeBuddy plugins from installed packages."""

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}
        self._discover()

    @property
    def plugins(self) -> dict[str, PluginBase]:
        return self._plugins

    def get_analyzer_checks(self, language: str) -> list[AnalyzerCheck]:
        """Get all analyzer checks applicable to a given language."""
        checks: list[AnalyzerCheck] = []
        for plugin in self._plugins.values():
            if language in plugin.languages:
                checks.extend(plugin.get_analyzer_checks())
        return checks

    def get_refactoring_patterns(self, language: str) -> list[RefactoringPattern]:
        """Get refactoring patterns for a language."""
        patterns: list[RefactoringPattern] = []
        for plugin in self._plugins.values():
            if language in plugin.languages:
                patterns.extend(plugin.get_refactoring_patterns())
        return patterns

    def get_scanner_rules(self, language: str) -> list[ScannerRule]:
        """Get scanner rules for a language."""
        rules: list[ScannerRule] = []
        for plugin in self._plugins.values():
            if language in plugin.languages:
                rules.extend(plugin.get_scanner_rules())
        return rules

    def _discover(self) -> None:
        """Discover plugins via the 'codebuddy.plugins' entry point group."""
        try:
            for ep in entry_points(group="codebuddy.plugins"):
                try:
                    plugin_class = ep.load()
                    plugin = plugin_class()
                    self._plugins[plugin.name] = plugin
                except Exception:
                    pass
        except TypeError:
            # Python <3.12 compatibility
            pass
