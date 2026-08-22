"""National statistical-office adapters.

Each module turns one agency's API into the same per-entity record shape used
by the rest of the pipeline (see ``docs/SCHEMA.md``).  They are deliberately
separate: the agencies disagree about geography codes, category definitions and
reference years, and squashing that into one "universal" fetcher would hide the
very incomparability the app has to display.

Run any of them directly, e.g.::

    python -m scripts.fetch_census.us_acs --level county
"""
