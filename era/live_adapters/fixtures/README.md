# ERA synthetic DCAD fixtures

The CSV files in this directory whose names contain `SYNTHETIC` are deliberately
fabricated test data. They contain no real-person records and are not copied,
transformed, sampled, or derived from Dallas CAD or any other production source.

The synthetic marker on every row is `ERA_SYNTHETIC_TEST_DATA_V1`. Values are
intentionally fictional and exist only to exercise leading-zero identifiers,
two-table joins, building/unit address composition, half-number composition,
legal-description assembly, and blank optional fields.

The separately ignored `*_FIXTURE.CSV` files are real-data excerpts. They are not
fallback inputs and must never be committed.
