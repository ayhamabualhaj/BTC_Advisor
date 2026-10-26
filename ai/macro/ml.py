"""Macro ML agent: learns from past macro setups and how the price moved after them."""

from ai import ml, similarity


def score(brief):
    return ml.score(similarity.encode(brief.setup), brief.training)
