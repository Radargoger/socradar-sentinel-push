# Test gate boundaries

The runner detects accidental empty discovery and missing executed checks. It
assumes trusted test code: a forged receipt followed by `os._exit(0)`, or an
empty check/require helper, can still produce a successful suite. These are
measured, documented limits, not protection against deliberately deceptive tests.
Review helper semantics and test changes independently; a receipt is not proof
that every intended assertion ran.
