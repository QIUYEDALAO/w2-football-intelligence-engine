# W2 Devig Methods V1

W2 Stage 6 compares four de-vig methods behind one interface.

## Methods

- `PROPORTIONAL`: normalize inverse decimal odds.
- `SHIN`: reduce overround with a bounded insider-style adjustment, then normalize.
- `POWER`: solve an exponent so powered implied probabilities sum to one.
- `LOGARITHMIC`: solve a log-space shift and normalize.

## Selection Rule

Method selection may use train and validation data only. Test data is reserved for final reporting.

## Failure Handling

Invalid odds, non-positive probabilities, or numerical failures must produce explicit diagnostics.
Fallback normalization is allowed for diagnostics, but the failure must remain visible.
