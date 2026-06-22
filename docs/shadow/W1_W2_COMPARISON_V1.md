# W1/W2 Shadow Comparison V1

Stage12B compares W1 frozen assets and W2 shadow outputs without importing W1
runtime code or calling a W1 prediction service.

Comparison fields:

- fixture identity and kickoff
- odds snapshot age and bookmaker coverage
- market probability
- mu/lambda and score distribution
- W2 independent probability and shadow decision
- data latency and runtime availability

Unavailable fields are explicitly marked `NOT_AVAILABLE`. W1 outputs are not
treated as ground truth.
