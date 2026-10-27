"""Database aliases (AD-3). Always pass one explicitly: `using=PERSONAL` / `using=CATALOG`.

`default` is the personal schema because Django requires a `default` alias and the user table
must share an alias with the personal data that references it.
"""

PERSONAL = "default"
CATALOG = "catalog"
