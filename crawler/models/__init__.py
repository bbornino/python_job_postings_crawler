"""
crawler.models package. Django only discovers models imported here, so every
model in every file below must be listed, or it silently gets no migrations.
"""

# TODO: replace with the model names from the current models.py once it's moved to companies.py
from .companies import *  # noqa: F401,F403
from .references import ReferenceCompanyEntry, ReferenceSource, ReferenceStateEntry  # noqa: F401

# Add when job postings get their models:
# from .job_postings import ...
