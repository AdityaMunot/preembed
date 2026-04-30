from hypothesis import settings

# Disable Hypothesis example database to avoid creating .hypothesis/ directory.
settings.register_profile("default", database=None)
settings.load_profile("default")
