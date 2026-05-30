"""
conftest.py — pytest test isolation.
Only applies to non-API test modules.
"""
# The api/tests already manage their own tmp dirs via _fresh_overrides().
# This conftest handles isolation for feature_store, ml, and other modules.
