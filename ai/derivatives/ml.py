"""Derivatives ML agent: learns from past derivatives setups and how the price moved after them."""

from ai import ml, similarity


def score(brief):
    return ml.score(similarity.encode(brief.setup), brief.training)
