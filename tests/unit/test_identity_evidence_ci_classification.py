from scripts.classify_ci import classify


def test_identity_evidence_generator_forces_full_ci() -> None:
    plan = classify(["scripts/arch_p1_03b_identity_evidence.py"])
    assert plan.full
    assert plan.verify
    assert plan.web
    assert plan.migration
    assert plan.compose
    assert plan.staging_parity
    assert plan.predeploy_e2e
