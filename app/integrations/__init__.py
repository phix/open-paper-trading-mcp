"""Stockade-owned integrations between the Hub and sibling forks.

Self-contained module area for cross-fork seams (e.g. backtrader -> Hub paper
execution). Nothing here is imported by the Hub's core request path; these are
opt-in glue components used by offline tooling.
"""
